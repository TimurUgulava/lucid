#!/usr/bin/env python3
"""Регрессия проверки сцен: отрицательные примеры должны ловиться, положительные — проходить.

Запуск: python3 evals/run_fixtures.py   (сначала evals/make_fixtures.py, если fixtures/ пуста)
Код выхода 1, если хоть одно ожидание не совпало.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "evals" / "fixtures"
spec_path = FIX / "scenes.json"
if not spec_path.exists():
    subprocess.run([sys.executable, str(ROOT / "evals" / "make_fixtures.py")], check=True)
spec = json.loads(spec_path.read_text(encoding="utf-8"))
report = FIX / "scene-checks.json"
subprocess.run([sys.executable, str(ROOT / "scripts" / "check_scenes.py"), "--scenes", str(spec_path), "--report", str(report)],
               capture_output=True, text=True)
res = json.loads(report.read_text(encoding="utf-8"))
by_scene = {}
for it in res["issues"]:
    by_scene.setdefault(it.get("scene"), set()).add(it["kind"])
ok = True
print("{:<28} {:<22} {:<28} {}".format("пример", "ожидание", "найдено", "итог"))
for sc in spec["scenes"]:
    found = by_scene.get(sc["id"], set())
    expect = set(sc["expect"])
    if expect:
        passed = expect.issubset(found)
    else:
        passed = not found
    ok &= passed
    print("{:<28} {:<22} {:<28} {}".format(sc["id"], ",".join(sorted(expect)) or "чисто", ",".join(sorted(found)) or "чисто", "ок" if passed else "ПРОВАЛ"))
print("итог:", "все ожидания совпали" if ok else "есть расхождения")
sys.exit(0 if ok else 1)
