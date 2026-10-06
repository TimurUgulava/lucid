#!/usr/bin/env python3
"""Сцены видео из script.md: scenes.json плюс заготовка HTML на каждую сцену.

Читает заголовок, строки «Одной фразой» и «Зачем тебе», блоки «## N. …» с
полями «Форма», «Данные формы», «Подпись», «Режиссура», «Нарратив» (нарратив
может занимать несколько строк до пустой строки или следующего поля). Создаёт:
  scenes/scenes.json      порядок сцен, нарратив, размер кадра
  scenes/00-title.html    титульник из scene-title.html: заголовок, обещание, образ
  scenes/NN-<форма>.html  по сцене на блок из scene-skeleton.html: раскладка по
                          форме, шапка и подпись заполнены, площадка пустая,
                          данные формы и режиссура в комментарии
  scenes/99-end.html      финал из scene-skeleton.html: «одной фразой» заголовком, «зачем тебе» подписью
Подпись каждой сцены получает data-role="caption" и data-after="@stage":
она появится только после всех объектов площадки. Существующие файлы сцен не
перезаписываются без --force; scenes.json обновляется всегда.
"""
import argparse
import json
import re
import sys
from html import escape
from pathlib import Path

FIELD_RE = re.compile(r"^(Форма|Данные формы|Подпись|Откуда|Пометка|Режиссура|Нарратив):\s*(.*)$")
LAYOUT_BY_FORM = {
    "timeline": "layout-wide", "trend": "layout-wide", "quantity": "layout-wide", "causal": "layout-wide", "compare": "layout-wide",
    "term": "layout-split", "structure": "layout-split", "slider": "layout-split", "decision": "layout-wide",
    "walkthrough": "layout-tall",
}


def parse_script(text):
    title, one_line, why, source = "", "", "", ""
    blocks, cur = [], None
    narr_mode = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        if line.startswith("> Одной фразой:"):
            one_line = line.split(":", 1)[1].strip()
            continue
        if line.startswith("> Зачем тебе:"):
            why = line.split(":", 1)[1].strip()
            continue
        if line.startswith("Источник:") and cur is None:
            source = line.split(":", 1)[1].strip()
            continue
        m = re.match(r"^##\s*(\d+)[.)]\s*(.+)$", line)
        if m:
            cur = {"n": int(m.group(1)), "title": m.group(2).strip(), "form": "", "data": "",
                   "caption": "", "direction": "", "narration": []}
            blocks.append(cur)
            narr_mode = False
            continue
        if cur is None:
            continue
        if not line.strip():
            narr_mode = False
            continue
        fm = FIELD_RE.match(line.strip())
        if fm:
            key, val = fm.groups()
            narr_mode = key == "Нарратив"
            if key == "Форма":
                cur["form"] = val.strip()
            elif key == "Данные формы":
                cur["data"] = val.strip()
            elif key == "Подпись":
                cur["caption"] = val.strip()
            elif key == "Режиссура":
                cur["direction"] = val.strip()
            elif key == "Нарратив":
                cur["narration"].append(val.strip())
            continue
        if narr_mode:
            cur["narration"].append(line.strip())
    for b in blocks:
        b["narration"] = " ".join(x for x in b["narration"] if x)
    return title, one_line, why, source, blocks


def sub1(s, pattern, repl):
    out, n = re.subn(pattern, lambda m: repl, s, count=1, flags=re.S)
    if n == 0:
        sys.stderr.write("предупреждение: в каркасе не найден шаблон {}\n".format(pattern[:40]))
    return out


def strip_period(s):
    s = re.sub(r"\.\s*$", "", s.strip())
    return s[:1].upper() + s[1:] if s else s


def fill_content(skeleton, n, total, title, caption, form, data, direction, source):
    s = skeleton
    s = sub1(s, r'<main class="scene layout-[a-z]+">', '<main class="scene {}">'.format(LAYOUT_BY_FORM.get(form, "layout-wide")))
    s = sub1(s, r'<p class="meta">.*?</p>', '<p class="meta">Блок {} из {}</p>'.format(n, total))
    s = sub1(s, r"<h1>.*?</h1>", "<h1>{}</h1>".format(escape(strip_period(title))))
    comment = "<!-- Форма: {}. Данные: {}{} -->".format(escape(form or "?"), escape(data or "см. script.md"),
                                                       (" Режиссура: " + escape(direction)) if direction else "")
    stage = '<section class="stage" id="stage">\n    {}\n    <!-- Нарисовать одну форму в SVG или HTML: объекты с id и data-at-word, подписи внутри объектов в их группах -->\n  </section>'.format(comment)
    s = sub1(s, r'<section class="stage" id="stage">.*?</section>', stage)
    cap = '<p class="caption" data-role="caption" data-at="0" data-after="@stage">{}</p>'.format(escape(strip_period(caption) if form == "end" else caption)) if caption else \
          '<p class="caption" data-role="caption" data-at="0" data-after="@stage"></p>'
    s = sub1(s, r'<p class="caption"[^>]*>.*?</p>', cap)
    s = sub1(s, r'<p class="source">.*?</p>', '<p class="source">{}</p>'.format(escape(source)))
    s = sub1(s, r'<p class="folio">.*?</p>', '<p class="folio">{:02d} / {:02d}</p>'.format(n + 1, total + 2))
    return s


def title_size(text):
    """Размер заголовка титула по длине фразы, относительно шкалы пресета: короткая крупно, длинная умещается в колонку."""
    n = len(text)
    k = 1 if n <= 24 else (0.87 if n <= 40 else (0.73 if n <= 60 else 0.63))
    return "" if k == 1 else ' style="font-size: calc(var(--t-title) * {})"'.format(k)


def fill_title(skeleton, meta, h1, deck, label, source, folio):
    s = skeleton
    s = sub1(s, r'<p class="meta">.*?</p>', '<p class="meta">{}</p>'.format(escape(meta)))
    s = sub1(s, r"<h1>.*?</h1>", "<h1{}>{}</h1>".format(title_size(h1), escape(strip_period(h1))))
    deck_style = '' if len(deck) <= 70 else ' style="font-size: var(--t-copy)"'  # длинное обещание — размером подписи
    s = sub1(s, r'<p class="deck">.*?</p>', '<p class="deck"{}>{}</p>'.format(deck_style, escape(strip_period(deck))))
    s = sub1(s, r'<p class="hero-label"[^>]*>.*?</p>', '<p class="hero-label" data-role="caption" data-at="0" data-after="@stage">{}</p>'.format(escape(label)))
    s = sub1(s, r'<p class="source">.*?</p>', '<p class="source">{}</p>'.format(escape(source)))
    s = sub1(s, r'<p class="folio">.*?</p>', '<p class="folio">{}</p>'.format(folio))
    return s


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--script", required=True, help="путь к script.md")
    p.add_argument("--out-dir", required=True, help="папка scenes")
    p.add_argument("--skeleton", required=True, help="assets/scene-skeleton.html из скилла")
    p.add_argument("--title-skeleton", default="", help="assets/scene-title.html; по умолчанию рядом со skeleton")
    p.add_argument("--size", default="1920x1080", help="размер кадра экспорта")
    p.add_argument("--fps", type=int, default=24)
    p.add_argument("--force", action="store_true", help="перезаписать существующие HTML сцен")
    args = p.parse_args()

    text = Path(args.script).read_text(encoding="utf-8")
    skeleton = Path(args.skeleton).read_text(encoding="utf-8")
    title_path = Path(args.title_skeleton) if args.title_skeleton else Path(args.skeleton).parent / "scene-title.html"
    title_skel = title_path.read_text(encoding="utf-8")
    title, one_line, why, source, blocks = parse_script(text)
    if not blocks:
        sys.stderr.write("В script.md нет блоков «## N. …»\n")
        sys.exit(1)
    missing = [b["n"] for b in blocks if not b["narration"]]
    if missing:
        sys.stderr.write("У блоков {} нет строки «Нарратив:»\n".format(", ".join(map(str, missing))))
        sys.exit(1)
    source_line = "Источник — " + source if source else "Источник — " + title

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    total = len(blocks)
    scenes = []

    def emit(sid, html):
        path = out / (sid + ".html")
        if path.exists() and not args.force:
            sys.stderr.write("есть, не трогаю: {}\n".format(path.name))
        else:
            path.write_text(html, encoding="utf-8")
        return sid + ".html"

    title_narr = ". ".join(strip_period(x) for x in [title, one_line, why] if x) + "."
    scenes.append({"id": "00-title", "file": emit("00-title", fill_title(title_skel, "Объяснение", title, why or one_line,
                                                                       "От материала к пониманию", source_line, "01 / {:02d}".format(total + 2))),
                   "narration": title_narr})
    for b in blocks:
        slug = re.sub(r"[^a-z0-9]+", "-", b["form"].lower()).strip("-") or "block"
        sid = "{:02d}-{}".format(b["n"], slug)
        html = fill_content(skeleton, b["n"], total, b["title"], b["caption"], b["form"], b["data"], b["direction"], source_line)
        scenes.append({"id": sid, "file": emit(sid, html), "narration": b["narration"]})
    end_html = fill_content(skeleton, total + 1, total, one_line or title, why, "end", "", "", source_line)
    end_html = sub1(end_html, r'<main class="scene layout-[a-z]+">', '<main class="scene layout-end">')
    if len(one_line or title) > 70:
        end_html = sub1(end_html, r"<h1>", '<h1 style="font-size: calc(var(--t-h) * 0.9)">')
    # подпись финала звучит после самой фразы: ждём её слова
    end_words = len(("Одной фразой. " + strip_period(one_line or title)).split())
    end_html = sub1(end_html, r'<p class="caption" data-role="caption" data-at="0" data-after="@stage">',
                    '<p class="caption" data-role="caption" data-at="0" data-at-word="{}" data-after="@stage">'.format(end_words))
    end_html = sub1(end_html, r'<p class="meta">.*?</p>', '<p class="meta">Одной фразой</p>')
    end_html = sub1(end_html, r'<section class="stage" id="stage">.*?</section>', '<section class="stage" id="stage"></section>')
    scenes.append({"id": "99-end", "file": emit("99-end", end_html),
                   "narration": "Одной фразой. " + strip_period(one_line or title) + "."})

    spec = {"size": args.size, "fps": args.fps, "design": "1920x1080", "scenes": scenes}
    (out / "scenes.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"scenes": len(scenes), "out": str(out / "scenes.json"),
                      "words": sum(len(s["narration"].split()) for s in scenes)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
