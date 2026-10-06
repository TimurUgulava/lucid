#!/usr/bin/env python3
"""Озвучка текста для lucid через Gemini TTS.

Команды:
  synth   один текстовый файл → один WAV
  scenes  scenes.json → audio/<id>.wav для каждой сцены + durations.json
  probe   короткая фраза несколькими голосами, чтобы выбрать голос на онбординге

Ключ Gemini ищется по порядку: переменная окружения GEMINI_API_KEY,
переменная GOOGLE_AI_API_KEY, запись macOS Keychain с именем сервиса
lucid-gemini-api-key. Нет ключа — скрипт печатает, как его получить, и
завершается с кодом 2.
"""
import argparse
import base64
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.8-flash-tts"
DEFAULT_VOICE = "Charon"
KEYCHAIN_SERVICE = "lucid-gemini-api-key"
NO_KEY_HELP = """Ключ Gemini не найден.

Как получить (бесплатно, нужен аккаунт Google):
  1. Открыть https://aistudio.google.com/apikey
  2. Нажать «Create API key», скопировать ключ.

Куда положить, любой из вариантов:
  • в оболочку:   export GEMINI_API_KEY='<ключ>'   (строка в ~/.zshrc или ~/.bashrc)
  • в Keychain macOS:
      security add-generic-password -a "$USER" -s lucid-gemini-api-key -w '<ключ>'

Без ключа видео не собирается; объяснение можно получить в виде HTML-страницы."""


def die(msg, code=1):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(code)


def find_key():
    for name in ("GEMINI_API_KEY", "GOOGLE_AI_API_KEY"):
        if os.environ.get(name):
            return os.environ[name].strip()
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                capture_output=True, text=True, timeout=10)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except Exception:
            pass
    return None


STAGE_RE = re.compile(r"\[[^\]\n]{1,80}\]")


def clean_text(text):
    """Убирает режиссёрские ремарки в квадратных скобках и лишние пробелы."""
    text = STAGE_RE.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_chunks(text, max_chars):
    """Режет текст по границам предложений, чтобы кусок не превышал max_chars."""
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    chunks, cur = [], ""
    for s in sentences:
        if not s:
            continue
        if len(cur) + len(s) + 1 > max_chars and cur:
            chunks.append(cur.strip())
            cur = s
        else:
            cur = (cur + " " + s).strip()
    if cur:
        chunks.append(cur.strip())
    return chunks


def gemini_request(key, model, voice, text, style):
    if style:
        text = "{}:\n\n{}".format(style.rstrip(":"), text)
    body = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    req = urllib.request.Request(
        API.format(model=model) + "?key=" + key,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    delays = [5, 15, 45]
    data = None
    for attempt in range(len(delays) + 1):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            detail = e.read()[:400].decode("utf-8", "replace")
            if e.code in (401, 403):
                die("Gemini отклонил ключ (HTTP {}): {}".format(e.code, detail))
            if e.code == 404:
                die("Модель {} не найдена (HTTP 404). Проверь --model.".format(model))
            if e.code in (429, 500, 503) and attempt < len(delays):
                sys.stderr.write("HTTP {}, повтор через {} с\n".format(e.code, delays[attempt]))
                time.sleep(delays[attempt])
                continue
            die("Gemini TTS: HTTP {}: {}".format(e.code, detail))
        except urllib.error.URLError as e:
            if attempt < len(delays):
                time.sleep(delays[attempt])
                continue
            die("Сеть недоступна: {}".format(e))
    try:
        part = data["candidates"][0]["content"]["parts"][0]["inlineData"]
    except (KeyError, IndexError, TypeError):
        die("Gemini вернул ответ без аудио: {}".format(json.dumps(data, ensure_ascii=False)[:400]))
    raw = base64.b64decode(part["data"])
    mime = part.get("mimeType", "")
    return raw, mime


def pcm_from_response(raw, mime):
    """Возвращает (pcm_bytes, rate). Модели отдают либо готовый WAV, либо сырой L16."""
    if raw[:4] == b"RIFF":
        with wave.open(io.BytesIO(raw), "rb") as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2:
                die("Неожиданный формат WAV от Gemini: каналов {}, байт на отсчёт {}".format(
                    w.getnchannels(), w.getsampwidth()))
            return w.readframes(w.getnframes()), w.getframerate()
    m = re.search(r"rate=(\d+)", mime)
    rate = int(m.group(1)) if m else 24000
    return raw, rate


def write_wav(path, pcm, rate):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


def synth_gemini(text, out, key, model, voice, style, max_chars, pause_ms):
    chunks = split_chunks(clean_text(text), max_chars)
    if not chunks:
        die("Пустой текст для озвучки")
    pcm_all, rate_all = b"", None
    for i, chunk in enumerate(chunks, 1):
        sys.stderr.write("  кусок {}/{} ({} знаков)\n".format(i, len(chunks), len(chunk)))
        raw, mime = gemini_request(key, model, voice, chunk, style)
        pcm, rate = pcm_from_response(raw, mime)
        if rate_all is None:
            rate_all = rate
        elif rate != rate_all:
            die("Частота дискретизации изменилась между кусками: {} и {}".format(rate_all, rate))
        if pcm_all and pause_ms:
            pcm_all += b"\x00\x00" * int(rate_all * pause_ms / 1000)
        pcm_all += pcm
    write_wav(out, pcm_all, rate_all)
    return len(pcm_all) / 2 / rate_all


def synth(text, out, args):
    key = find_key()
    if not key:
        die(NO_KEY_HELP, 2)
    return synth_gemini(text, out, key, args.model, args.voice, args.style, args.max_chars, args.pause_ms)


def maybe_mp3(wav_path, want):
    if not want:
        return
    mp3 = Path(wav_path).with_suffix(".mp3")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav_path),
                        "-codec:a", "libmp3lame", "-q:a", "3", str(mp3)])
    if r.returncode != 0:
        sys.stderr.write("mp3 не собрался: ffmpeg вернул {}\n".format(r.returncode))


def cmd_synth(args):
    text = Path(args.text_file).read_text(encoding="utf-8")
    dur = synth(text, args.out, args)
    maybe_mp3(args.out, args.mp3)
    print(json.dumps({"out": str(args.out), "seconds": round(dur, 2)}, ensure_ascii=False))


def cmd_scenes(args):
    spec = json.loads(Path(args.scenes).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dur_path = out_dir / "durations.json"
    durations = json.loads(dur_path.read_text()) if dur_path.exists() else {}
    only = set(args.only.split(",")) if args.only else None
    for sc in spec["scenes"]:
        sid = sc["id"]
        if only and sid not in only:
            continue
        narration = sc.get("narration", "").strip()
        wav = out_dir / (sid + ".wav")
        if not narration:
            sys.stderr.write("Сцена {}: нарратива нет, тишина {} с\n".format(sid, args.silent_seconds))
            write_wav(wav, b"\x00\x00" * int(24000 * args.silent_seconds), 24000)
            durations[sid] = float(args.silent_seconds)
            continue
        sys.stderr.write("Сцена {}: {} слов\n".format(sid, len(narration.split())))
        durations[sid] = round(synth(narration, wav, args), 3)
        maybe_mp3(wav, args.mp3)
    dur_path.write_text(json.dumps(durations, ensure_ascii=False, indent=2))
    total = sum(durations[s["id"]] for s in spec["scenes"] if s["id"] in durations)
    print(json.dumps({"durations": str(dur_path), "scenes": len(durations),
                      "total_seconds": round(total, 1)}, ensure_ascii=False))


def cmd_probe(args):
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for voice in args.voices.split(","):
        voice = voice.strip()
        if not voice:
            continue
        args.voice = voice
        wav = out_dir / (voice + ".wav")
        sys.stderr.write("Голос {}\n".format(voice))
        results[voice] = round(synth(args.text, wav, args), 2)
        maybe_mp3(wav, args.mp3)
    print(json.dumps({"out_dir": str(out_dir), "seconds": results}, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", default=DEFAULT_MODEL, help="модель Gemini TTS, по умолчанию " + DEFAULT_MODEL)
    common.add_argument("--voice", default=DEFAULT_VOICE, help="голос Gemini, по умолчанию " + DEFAULT_VOICE)
    common.add_argument("--style", default="",
                        help="инструкция манеры чтения перед текстом, например «Read calmly, at a lecturer's pace»")
    common.add_argument("--max-chars", type=int, default=2500, help="предел знаков на один запрос")
    common.add_argument("--pause-ms", type=int, default=250, help="тишина между кусками одного текста")
    common.add_argument("--mp3", action="store_true", help="рядом с WAV положить MP3 через ffmpeg")
    sub = p.add_subparsers(dest="cmd")
    sub.required = True

    s1 = sub.add_parser("synth", parents=[common], help="текстовый файл → WAV")
    s1.add_argument("--text-file", required=True)
    s1.add_argument("--out", required=True, help="путь к WAV")
    s1.set_defaults(func=cmd_synth)

    s2 = sub.add_parser("scenes", parents=[common], help="scenes.json → WAV на сцену + durations.json")
    s2.add_argument("--scenes", required=True, help="путь к scenes.json")
    s2.add_argument("--out-dir", required=True, help="папка для audio")
    s2.add_argument("--only", default="", help="озвучить только эти id через запятую")
    s2.add_argument("--silent-seconds", type=float, default=3.0, help="длина сцены без нарратива")
    s2.set_defaults(func=cmd_scenes)

    s3 = sub.add_parser("probe", parents=[common], help="проба голосов для онбординга")
    s3.add_argument("--voices", default="Charon,Kore,Puck,Sulafat", help="голоса через запятую")
    s3.add_argument("--out-dir", required=True)
    s3.add_argument("--text", default="Это проба голоса. Так будет звучать объяснение: короткие фразы, одна мысль за раз.")
    s3.set_defaults(func=cmd_probe)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
