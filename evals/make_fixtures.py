#!/usr/bin/env python3
"""Собирает контрольные сцены для check_scenes.py из каркаса assets/scene-skeleton.html.

Отрицательные примеры (проверка обязана найти дефект) и положительные
(проверка обязана промолчать). Пишет evals/fixtures/<id>.html и
evals/fixtures/scenes.json с ожиданиями. Запуск: python3 evals/make_fixtures.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKEL = (ROOT / "assets" / "scene-skeleton.html").read_text(encoding="utf-8")
OUT = ROOT / "evals" / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)

NARR = ("Первый шаг готовит материал. Второй шаг превращает его в схему. Третий шаг проверяет схему по источнику "
        "и возвращает на правку, если что-то разошлось.")


def base():
    return SKEL


def sub(s, pattern, repl, count=1):
    out, n = re.subn(pattern, lambda m: repl, s, count=count, flags=re.S)
    assert n >= 1, pattern[:50]
    return out


fixtures = []


def add(fid, html, expect, note):
    (OUT / (fid + ".html")).write_text(html, encoding="utf-8")
    fixtures.append({"id": fid, "file": fid + ".html", "narration": NARR, "expect": expect, "note": note})


# 1. Подпись пересекает возвратную линию
s = base()
s = sub(s, r'(<text x="864" y="336" text-anchor="middle" class="svg-copy">Второй шаг</text>)',
        r'\1\n        <text x="864" y="258" text-anchor="middle" class="svg-note">После правки — повторная проверка</text>'.replace("\\1", '<text x="864" y="336" text-anchor="middle" class="svg-copy">Второй шаг</text>'))
add("neg-01-line-cross", s, ["lineOverlaps"], "подпись лежит на линии таймлайна")

# 2. Подпись без зависимости от рисунка
s = base()
s = sub(s, r'<p class="caption" data-role="caption" data-at="0" data-after="@stage">', '<p class="caption" data-role="caption" data-at="0">')
add("neg-02-caption-early", s, ["зависимости"], "внешняя подпись не ждёт объекты")

# 3. Формально крупный шрифт, но SVG-масштаб делает буквы мелкими
s = base()
s = sub(s, r'<svg viewBox="0 0 1728 500"', '<svg viewBox="0 0 4320 1250"')
add("neg-03-svg-scale", s, ["smallText"], "viewBox в 2,5 раза больше площадки, текст 30 px становится 12 px")

# 4. Текст читается на фоне страницы, но теряется на карточке
s = base()
s = sub(s, r'<circle cx="200" cy="250" r="30" class="card"/>',
        '<rect x="60" y="300" width="280" height="110" rx="8" fill="var(--ink-dim)" id="card-1"/>')
add("neg-04-card-contrast", s, ["lowContrast"], "подпись первого шага легла на карточку цвета текста")

# 5. Иллюстрация закрывает строку источника
s = base()
s = sub(s, r'<p class="folio">', '<div id="late-plane" style="position:absolute;left:80px;bottom:30px;width:600px;height:70px;background:var(--accent)"></div>\n  <p class="folio">')
add("neg-05-occlusion-source", s, ["occlusion"], "поздняя плоскость перекрывает строку источника")

# 6. Подпись ссылается на неизвестный объект и на скрытого родителя
s = base()
s = sub(s, r'(<p class="caption" data-role="caption" data-at="0" )data-after="@stage"', '<p class="caption" data-role="caption" data-at="0" data-after="step-1,nope"')
add("neg-06-unknown-id", s, ["зависимости"], "в data-after неизвестный id")
s = base()
s = sub(s, r'<g id="step-3" data-at-word="15">', '<g id="step-3" data-at-word="15" style="display:none">')
s = sub(s, r'(<p class="caption" data-role="caption" data-at="0" )data-after="@stage"', '<p class="caption" data-role="caption" data-at="0" data-after="step-3"')
add("neg-06b-hidden-parent", s, ["зависимости"], "подпись ждёт скрытый объект")

# 7. Повторная подготовка или перемотка меняют результат
s = base()
s = sub(s, r'</script>\n</body>', '</script>\n<script>(function(){var orig=window.lucidSeek;window.lucidSeek=function(ms){orig(ms);var el=document.querySelector("#step-2");el.style.opacity=(Math.random()*0.5+0.5).toFixed(3);};})();</script>\n</body>')
add("neg-07-nondeterministic", s, ["детерминизм"], "перемотка даёт случайную прозрачность")

# 8. Два соседних текстовых блока пересекаются при реальной загрузке шрифта
s = base()
s = sub(s, r'<p class="caption" data-role="caption" data-at="0" data-after="@stage">(.*?)</p>',
        '<p class="caption" data-role="caption" data-at="0" data-after="@stage">Что видно на схеме: главное выделено, одно-два предложения, и ещё одна длинная строка подписи, которая занимает две строки кадра</p>\n  <p class="note" style="position:absolute;left:96px;top:930px;width:1728px">Второй абзац стоит слишком близко и наезжает на подпись при реальной высоте строки</p>')
add("neg-08-text-overlap", s, ["textOverlaps"], "два абзаца пересекаются по высоте")

# 9. Наконечник возвратной стрелки заходит за изгиб: плечо короче головки
ARROW_DEFS = '<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="var(--accent)"/></marker></defs>'
s = base()
s = sub(s, r'<path class="line" d="M100 250H1628"/>', ARROW_DEFS + '\n      <path class="line" d="M100 250H1628"/>\n      <path class="link" id="return-short" d="M1400 420V470H1200V452" marker-end="url(#ah)" data-at="0.2"/>')
add("neg-09-arrowhead", s, ["arrowheads"], "последнее плечо 18 единиц короче головки при штрихе 5")

# 10. Две линии пересекаются без узла ветвления
s = base()
s = sub(s, r'<path class="line" d="M100 250H1628"/>', '<path class="line" d="M100 250H1628"/>\n      <path class="link" id="cross-a" d="M300 100V420" data-at="0.2"/>\n      <path class="link" id="cross-b" d="M200 300H500" data-at="0.3"/>')
add("neg-10-line-cross", s, ["lineCrossings"], "две линии пересекаются в середине без data-junction")

# 11. Гарнитура без кириллицы: браузер молча подменяет её системной
s = base()
s = sub(s, r'<link href="https://fonts\.googleapis\.com/[^"]+" rel="stylesheet">', '<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@400;700&display=swap" rel="stylesheet">')
s = sub(s, r"--display: '[^']+', Georgia, serif;", "--display: 'Fraunces', Georgia, serif;")
add("neg-11-no-cyrillic", s, ["шрифт"], "заголовочная гарнитура без кириллицы")

# Положительные
s = base()
s = sub(s, r'<circle cx="200" cy="250" r="30" class="card"/>',
        '<rect x="40" y="280" width="320" height="150" rx="8" class="card" id="card-ok"/>')
add("pos-01-text-in-shape", s, [], "текст внутри своей карточки с отступом")

s = base()
s = sub(s, r'<p class="caption" data-role="caption" data-at="0" data-after="@stage">(.*?)</p>', '')
s = sub(s, r'(<text x="1528" y="396" text-anchor="middle" class="svg-note">подпись</text>)',
        '<text x="1528" y="396" text-anchor="middle" class="svg-note">подпись</text>\n        <text x="864" y="460" text-anchor="middle" class="svg-note">Подпись в группе объекта появляется вместе с ним</text>')
add("pos-02-caption-in-group", s, [], "подпись лежит в группе объекта, внешней подписи нет")

s = base()
s = sub(s, r'<p class="meta">', '<div data-decor style="position:absolute;left:0;top:0;width:900px;height:1080px;background:var(--bg-2)"></div>\n  <p class="meta">')
s = sub(s, r'<path class="line" d="M100 250H1628"/>', '<path class="line" d="M100 250H1628" data-under/>\n      <text x="520" y="258" text-anchor="middle" class="svg-note" data-on-line>метка на линии намеренно</text>')
add("pos-03-decor-and-on-line", s, [], "декоративная плоскость и намеренная метка на линии")

s = base()
s = sub(s, r'<path class="line" d="M100 250H1628"/>', '<g data-junction="fork"><path class="line" d="M100 250H1628"/>\n      <path class="link" id="fork-a" d="M400 250V120" data-at="0.2"/>\n      <path class="link" id="fork-b" d="M400 250V380" data-at="0.3"/></g>')
add("pos-04-junction", s, [], "линии сходятся в узле ветвления, помеченном data-junction")

s = base()
s = sub(s, r'<path class="line" d="M100 250H1628"/>', ARROW_DEFS + '\n      <path class="line" d="M100 250H1628"/>\n      <path class="link" id="return-long" d="M1400 420V470H1200V380" marker-end="url(#ah)" data-at="0.2"/>')
add("pos-05-arrowhead-ok", s, [], "плечо 90 единиц длиннее головки с зазором")

(OUT / "scenes.json").write_text(json.dumps({"size": "1920x1080", "fps": 24, "design": "1920x1080", "scenes": fixtures},
                                            ensure_ascii=False, indent=2), encoding="utf-8")
print("фикстур:", len(fixtures), "→", OUT)
