#!/usr/bin/env python3
"""Проверка script.md на правила простого языка и верность чисел.

Нарушения (код выхода 1):
  • предложение длиннее предела в словах (по умолчанию 20);
  • больше предложений в подписи или абзаце, чем разрешено (по умолчанию 3);
  • заголовок блока «## N. …» длиннее предела в словах (по умолчанию 10).

Предупреждения (код выхода 0, с --strict — нарушения):
  • число из объяснения не найдено в source.md (если указан --source);
  • оригинал в скобках: «(legwork)», «(oversight)» — больше одного на блок;
  • латинские слова в тексте объяснения — больше одного на блок;
  • слово от 16 букв.

Не проверяются: строки «Откуда:», «Данные формы:», «Форма:», «Пометка:»,
«Источник:», строки с «якорь:», таблицы, код, frontmatter. Строки нарратива
проверяются только на длину предложения.
"""
import argparse
import re
import sys
from pathlib import Path

SKIP_PREFIXES = ("Откуда:", "Данные формы:", "Форма:", "Пометка:", "Источник:", "|", "```", "---")
CHECK_PREFIXES = ("Подпись:", "Нарратив:", "> Одной фразой:", "> Зачем тебе:")
SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[«\"(\[A-ZА-ЯЁ0-9])")
WORD = re.compile(r"[\w'’-]+", re.UNICODE)
NUM = re.compile(r"(?<![\w.])\d[\d   ]*(?:[.,]\d+)?%?")
LATIN_WORD = re.compile(r"(?<![\w-])[A-Za-z][A-Za-z0-9-]{1,}(?![\w-])")
PAREN_LATIN = re.compile(r"\(\s*[A-Za-z][^)]{0,60}\)")


def words(s):
    return [w for w in WORD.findall(s) if re.search(r"[^\W_]", w)]


def norm_num(s):
    s = s.replace(" ", "").replace(" ", "").replace(" ", "").replace(",", ".")
    return s.rstrip(".")


def strip_markdown(s):
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"\*(.+?)\*", r"\1", s)
    s = re.sub(r"`[^`]*`", "", s)
    return s


def strip_quotes(s):
    """Цитаты в «…» не считаются текстом объяснения."""
    return re.sub(r"«[^»]*»", "", s)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("script", help="путь к script.md")
    p.add_argument("--source", default="", help="source.md для сверки чисел")
    p.add_argument("--max-words", type=int, default=20)
    p.add_argument("--max-sentences", type=int, default=3)
    p.add_argument("--max-title-words", type=int, default=10)
    p.add_argument("--long-word", type=int, default=16, help="длина слова, с которой оно считается длинным")
    p.add_argument("--strict", action="store_true", help="предупреждения считать нарушениями")
    args = p.parse_args()

    text = Path(args.script).read_text(encoding="utf-8")
    lines = text.splitlines()
    issues, warnings = [], []
    in_code, in_front, in_narration = False, False, False
    script_numbers = []
    block = "шапка"
    per_block = {}  # block -> {"latin": [...], "paren": [...]}

    def bucket():
        return per_block.setdefault(block, {"latin": [], "paren": []})

    for i, raw in enumerate(lines, 1):
        line = raw.strip()
        if i == 1 and line == "---":
            in_front = True
            continue
        if in_front:
            if line == "---":
                in_front = False
            continue
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not line:
            in_narration = False
            continue
        if line.startswith("## "):
            in_narration = False
            title = re.sub(r"^##\s*\d+[.)]?\s*", "", line)
            block = title[:40]
            n = len(words(title))
            if n > args.max_title_words:
                issues.append("строка {}: заголовок блока {} слов (предел {}): «{}»".format(
                    i, n, args.max_title_words, title))
            for m in LATIN_WORD.finditer(strip_quotes(title)):
                bucket()["latin"].append(m.group(0))
            continue
        if line.startswith("#"):
            in_narration = False
            continue
        if line.startswith(SKIP_PREFIXES) or "якорь:" in line:
            in_narration = False
            continue
        body = line
        narration = in_narration
        for pref in CHECK_PREFIXES:
            if line.startswith(pref):
                body = line[len(pref):].strip()
                narration = pref == "Нарратив:"
                break
        in_narration = narration
        body = strip_markdown(body)
        if not body:
            continue
        script_numbers += [(i, m.group(0)) for m in NUM.finditer(body)]
        plain = strip_quotes(body)
        for m in PAREN_LATIN.finditer(plain):
            bucket()["paren"].append(m.group(0))
        for m in LATIN_WORD.finditer(re.sub(r"\([^)]*\)", "", plain)):
            bucket()["latin"].append(m.group(0))
        for w in words(plain):
            if len(w) >= args.long_word and re.search(r"[А-Яа-яЁё]", w):
                warnings.append("строка {}: длинное слово «{}»".format(i, w))
        sentences = [s for s in SENT_SPLIT.split(body) if s.strip()]
        if not narration and len(sentences) > args.max_sentences:
            issues.append("строка {}: {} предложений в абзаце (предел {})".format(i, len(sentences), args.max_sentences))
        for s in sentences:
            n = len(words(s))
            if n > args.max_words:
                issues.append("строка {}: предложение из {} слов (предел {}): «{}»".format(
                    i, n, args.max_words, s.strip()[:90]))

    for name, b in per_block.items():
        if len(b["paren"]) > 1:
            warnings.append("блок «{}»: оригинал в скобках {} раз: {}".format(name, len(b["paren"]), ", ".join(b["paren"])))
        if len(b["latin"]) > 1:
            warnings.append("блок «{}»: латинских слов {}: {}".format(name, len(b["latin"]), ", ".join(sorted(set(b["latin"])))))

    if args.source:
        src = Path(args.source).read_text(encoding="utf-8")
        src_norm = re.sub(r"(?<=\d)[   ](?=\d)", "", src).replace(",", ".")
        src_nums = set(norm_num(m.group(0)) for m in NUM.finditer(src))
        for i, raw_num in script_numbers:
            n = norm_num(raw_num)
            bare = n.rstrip("%")
            if n in src_nums or bare in src_nums or bare in src_norm:
                continue
            if re.fullmatch(r"\d{1,2}", bare):
                continue
            warnings.append("строка {}: число {} не найдено в источнике".format(i, raw_num.strip()))

    if args.strict:
        issues += warnings
        warnings = []
    for w in warnings:
        print("предупреждение: " + w)
    for s in issues:
        print("нарушение: " + s)
    if not issues and not warnings:
        print("ок: замечаний нет")
    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()
