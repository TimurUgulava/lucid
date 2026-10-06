#!/usr/bin/env python3
"""Проверка собранной страницы lucid в безголовом Chromium.

На ширинах 1920 и 390 px: ошибки консоли, горизонтальный перелив, битые
якоря навигации, пустые блоки без визуальной формы, наличие раздела «За
кадром». С --shots кладёт снимки шапки и каждого
блока в папку. Код выхода 1, если что-то не так.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_scenes import QA_JS  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("page", help="путь к index.html")
    p.add_argument("--shots", default="", help="папка для снимков (1920x1080)")
    p.add_argument("--widths", default="1920,390", help="ширины через запятую")
    p.add_argument("--min-text", type=float, default=12.0, help="минимальный размер текста, px; служебный текст страницы от 12")
    p.add_argument("--contrast", type=float, default=4.5)
    args = p.parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.stderr.write("Playwright не установлен: pip3 install playwright && python3 -m playwright install chromium\n")
        sys.exit(2)

    page_path = Path(args.page).resolve()
    if not page_path.exists():
        sys.stderr.write("Нет файла {}\n".format(page_path))
        sys.exit(2)
    problems, report = [], {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for w in (int(x) for x in args.widths.split(",")):
            errors = []
            pg = browser.new_page(viewport={"width": w, "height": 1080 if w > 900 else 844})
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            pg.goto(page_path.as_uri(), wait_until="load")
            pg.wait_for_timeout(900)
            pg.evaluate("document.querySelectorAll('.reveal').forEach(e => e.classList.add('in'))")
            info = pg.evaluate("""() => {
                const blocks = [...document.querySelectorAll('section.block')];
                const empty = blocks.filter(b => { const v = b.querySelector('.visual'); return !v || (v.querySelectorAll('*').length === 0 && v.textContent.trim().length < 20); }).map(b => b.id || '(без id)');
                const noSource = blocks.filter(b => !b.querySelector('details.source')).map(b => b.id || '(без id)');
                const links = [...document.querySelectorAll('nav a[href^="#"]')];
                const broken = links.filter(a => !document.querySelector(a.getAttribute('href'))).map(a => a.getAttribute('href'));
                return {
                    overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
                    blocks: blocks.length, empty, noSource, broken,
                    tail: !!document.getElementById('tail'),
                    h2: document.querySelectorAll('section.block h2').length,
                };
            }""")
            info["console_errors"] = errors
            pg.evaluate("document.fonts ? document.fonts.ready : null")
            qa = pg.evaluate(QA_JS, {"scale": 1, "minText": args.min_text, "lineGap": 6, "cardPad": 8, "contrast": args.contrast, "presentOpacity": 0.3})
            info["readability"] = {k: qa[k] for k in ("smallText", "textOverlaps", "lineOverlaps", "cardOverflow", "occlusion", "lowContrast", "needsEyes")}
            for kind in ("smallText", "textOverlaps", "lineOverlaps", "occlusion", "lowContrast"):
                for v in qa[kind][:12]:
                    problems.append("{}px: {}: {}".format(w, kind, json.dumps(v, ensure_ascii=False)))
            report[w] = info
            if errors:
                problems.append("{}px: ошибки консоли: {}".format(w, "; ".join(errors)[:300]))
            if info["overflow"]:
                problems.append("{}px: горизонтальный перелив".format(w))
            if info["broken"]:
                problems.append("{}px: битые якоря навигации: {}".format(w, ", ".join(info["broken"])))
            if info["empty"]:
                problems.append("{}px: блоки без визуальной формы: {}".format(w, ", ".join(info["empty"])))
            if info["noSource"]:
                problems.append("{}px: блоки без «Откуда это»: {}".format(w, ", ".join(info["noSource"])))
            if not info["blocks"]:
                problems.append("{}px: нет ни одного section.block".format(w))
            if not info["tail"]:
                problems.append("{}px: нет раздела #tail «За кадром»".format(w))
            if args.shots and w > 900:
                out = Path(args.shots)
                out.mkdir(parents=True, exist_ok=True)
                pg.screenshot(path=str(out / "00-hero.png"))
                for n, b in enumerate(pg.query_selector_all("section.block"), 1):
                    b.scroll_into_view_if_needed()
                    pg.wait_for_timeout(150)
                    pg.screenshot(path=str(out / "{:02d}-block.png".format(n)))
            pg.close()
        browser.close()
    print(json.dumps(report, ensure_ascii=False, indent=1))
    for pr in problems:
        print("проблема: " + pr)
    if not problems:
        print("ок: страница проходит проверку")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
