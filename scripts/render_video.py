#!/usr/bin/env python3
"""Сборка видео lucid: сцены в HTML + озвучка → video.mp4.

Каждая сцена записывается покадрово: страница открывается в Chromium через
Playwright, на каждый кадр вызывается window.lucidSeek(ms) и снимается
скриншот. Кадры и звук сцены склеивает ffmpeg в сегмент, сегменты — в
итоговый файл. Запись детерминированная: один и тот же кадр на одном и
том же времени при любом повторе.

Требует: playwright с Chromium (pip3 install playwright && python3 -m playwright
install chromium), ffmpeg в PATH.
"""
import argparse
import json
import math
import shutil
import subprocess
import sys
import wave
from pathlib import Path


def die(msg, code=1):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(code)


def check_tools():
    if not shutil.which("ffmpeg"):
        die("ffmpeg не найден. macOS: brew install ffmpeg; Linux: пакетный менеджер.")
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        die("Playwright не установлен:\n  pip3 install playwright && python3 -m playwright install chromium")


def wav_seconds(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def load_durations(audio_dir, scenes):
    dur_path = Path(audio_dir) / "durations.json"
    durations = json.loads(dur_path.read_text()) if dur_path.exists() else {}
    for sc in scenes:
        sid = sc["id"]
        wav = Path(audio_dir) / (sid + ".wav")
        if sid not in durations:
            if not wav.exists():
                die("Нет озвучки для сцены {}: ожидался {}. Сначала tts.py scenes.".format(sid, wav))
            durations[sid] = wav_seconds(wav)
    return durations


def record_scene(page, html_path, out_frames, seconds, fps, pad, scale, narration_words):
    out_frames.mkdir(parents=True, exist_ok=True)
    for old in out_frames.glob("*.jpg"):
        old.unlink()
    page.goto(html_path.resolve().as_uri(), wait_until="load")
    page.evaluate("document.fonts ? document.fonts.ready : null")
    page.wait_for_timeout(150)
    has_seek = page.evaluate("typeof window.lucidSeek === 'function'")
    if not has_seek:
        die("В сцене {} нет window.lucidSeek. Сцена собирается из assets/scene-skeleton.html.".format(html_path.name))
    if abs(scale - 1.0) > 1e-3:
        # сцена свёрстана под размер design; при другом viewport масштабируем целиком
        page.add_style_tag(content="html{{transform:scale({:.5f});transform-origin:0 0;}}".format(scale))
    page.evaluate("a => { window.lucidTiming = a; }", {"words": narration_words, "seconds": seconds})
    page.evaluate("window.lucidPrepare && window.lucidPrepare()")
    n_frames = int(math.ceil((seconds + pad) * fps))
    for i in range(n_frames):
        t_ms = i * 1000.0 / fps
        page.evaluate("t => window.lucidSeek(t)", t_ms)
        page.screenshot(path=str(out_frames / "{:05d}.jpg".format(i)), type="jpeg", quality=86)
        if i % (fps * 5) == 0:
            sys.stderr.write("    {:5.1f} с / {:.1f}\n".format(t_ms / 1000, seconds + pad))
    return n_frames


def encode_segment(frames_dir, wav, out_mp4, fps):
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-framerate", str(fps), "-i", str(frames_dir / "%05d.jpg"),
        "-i", str(wav),
        "-filter_complex", "[1:a]apad[a]",
        "-map", "0:v", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-shortest", "-movflags", "+faststart",
        str(out_mp4),
    ]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        die("ffmpeg не собрал сегмент {}".format(out_mp4))


def concat_segments(segments, out):
    lst = out.parent / ".render" / "concat.txt"
    lst.parent.mkdir(parents=True, exist_ok=True)
    lst.write_text("".join("file '{}'\n".format(str(p.resolve()).replace("'", "'\\''")) for p in segments))
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                        "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(out)])
    if r.returncode != 0:
        die("ffmpeg не склеил сегменты")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scenes", required=True, help="путь к scenes.json")
    p.add_argument("--audio-dir", required=True, help="папка с <id>.wav и durations.json")
    p.add_argument("--out", required=True, help="итоговый mp4")
    p.add_argument("--size", default="", help="ШИРИНАxВЫСОТА кадра, по умолчанию из scenes.json или 1920x1080; сцены свёрстаны под design из scenes.json и масштабируются")
    p.add_argument("--fps", type=int, default=0, help="кадров в секунду, по умолчанию из scenes.json или 24")
    p.add_argument("--pad", type=float, default=0.6, help="тишина в конце сцены, секунд")
    p.add_argument("--only", default="", help="перерисовать только эти id через запятую; склейка идёт из всех сегментов")
    p.add_argument("--fast", action="store_true", help="черновик: 1280x720 и 12 кадров в секунду")
    p.add_argument("--keep-frames", action="store_true", help="не удалять кадры после сборки")
    p.add_argument("--skip-checks", action="store_true", help="не гонять check_scenes.py до записи и после склейки")
    args = p.parse_args()

    check_tools()
    from playwright.sync_api import sync_playwright

    spec_path = Path(args.scenes)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    scenes = spec["scenes"]
    size = args.size or spec.get("size", "1920x1080")
    fps = args.fps or int(spec.get("fps", 24))
    if args.fast:
        size, fps = "1280x720", 12
    width, height = (int(x) for x in size.lower().split("x"))
    design_w, design_h = (int(x) for x in spec.get("design", "1920x1080").lower().split("x"))
    scale = min(width / design_w, height / design_h)

    out = Path(args.out)
    work = out.parent / ".render"
    seg_dir = work / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    durations = load_durations(args.audio_dir, scenes)
    only = set(args.only.split(",")) if args.only else None
    if args.fast:
        sys.stderr.write("черновик: 1280x720 при 12 кадрах, не выдавать как финал\n")
    checker = Path(__file__).resolve().parent / "check_scenes.py"
    if not args.skip_checks:
        cmd = [sys.executable, str(checker), "--scenes", str(spec_path), "--audio-dir", args.audio_dir,
               "--report", str(work / "scene-checks.json"), "--pad", str(args.pad)]
        if args.only:
            cmd += ["--only", args.only]
        work.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(cmd)
        if r.returncode != 0:
            die("Сцены не прошли проверку, отчёт: {}. Исправь сцены и повтори; --skip-checks только для черновика.".format(work / "scene-checks.json"))

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
        page = ctx.new_page()
        for sc in scenes:
            sid = sc["id"]
            if only and sid not in only:
                continue
            html = spec_path.parent / sc["file"]
            if not html.exists():
                die("Нет файла сцены {}".format(html))
            sys.stderr.write("Сцена {}: {:.1f} с\n".format(sid, durations[sid]))
            frames = work / "frames" / sid
            record_scene(page, html, frames, durations[sid], fps, args.pad, scale,
                         len(sc.get("narration", "").split()))
            encode_segment(frames, Path(args.audio_dir) / (sid + ".wav"), seg_dir / (sid + ".mp4"), fps)
            if not args.keep_frames:
                shutil.rmtree(frames, ignore_errors=True)
        browser.close()

    segments = [seg_dir / (sc["id"] + ".mp4") for sc in scenes]
    missing = [s.name for s in segments if not s.exists()]
    if missing:
        die("Нет сегментов для сцен: {}. Прогони без --only.".format(", ".join(missing)))
    concat_segments(segments, out)
    total = sum(durations[sc["id"]] + args.pad for sc in scenes)
    if not args.skip_checks:
        r = subprocess.run([sys.executable, str(checker), "--scenes", str(spec_path), "--audio-dir", args.audio_dir,
                            "--video", str(out), "--only", "__none__", "--pad", str(args.pad),
                            "--report", str(work / "video-checks.json")])
        if r.returncode != 0:
            die("Экспорт не прошёл проверку, отчёт: {}".format(work / "video-checks.json"))
    print(json.dumps({"out": str(out), "scenes": len(scenes), "seconds": round(total, 1),
                      "size": size, "fps": fps}, ensure_ascii=False))


if __name__ == "__main__":
    main()
