#!/usr/bin/env python3
"""Собирает установочный архив мода: python3 tools/package/build.py [версия]
Выход: dist/VARKA-<версия>.zip (версия по умолчанию — v0.26).

Внутри архива в корне лежит gamedata/ — стандартный вид мода для Anomaly:
  - Mod Organizer 2: Install a new mod from an archive → выбрать zip, MO2 сам узнает gamedata/;
  - вручную: распаковать zip в корень игры (туда, где bin/ и gamedata/), согласиться на слияние папок.

Раскладка:  src/*.script, src/varka/  → gamedata/scripts/
            src/configs/              → gamedata/configs/
            LICENSE, LICENSING.md, УСТАНОВКА.txt → корень архива (рядом с gamedata/)
tools/, doc/, parked/ в архив не идут: это верстак, не мод.
Архив детерминированный: одинаковые исходники дают байт-в-байт одинаковый zip.
"""
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "src")
HERE = os.path.dirname(os.path.abspath(__file__))
VERSION = sys.argv[1] if len(sys.argv) > 1 else "v0.26"
STAMP = (2026, 1, 1, 0, 0, 0)  # одна дата у всех файлов — иначе zip меняется от каждого checkout


def layout():
    """[(путь в архиве, путь на диске)] в порядке сортировки."""
    out = []
    for name in os.listdir(SRC):
        if name.endswith(".script"):
            out.append(("gamedata/scripts/" + name, os.path.join(SRC, name)))
    for sub, dst in (("varka", "gamedata/scripts/varka"), ("configs", "gamedata/configs")):
        base = os.path.join(SRC, sub)
        for d, _, files in os.walk(base):
            for f in files:
                rel = os.path.relpath(os.path.join(d, f), base).replace(os.sep, "/")
                out.append((dst + "/" + rel, os.path.join(d, f)))
    out.append(("LICENSE", os.path.join(ROOT, "LICENSE")))
    out.append(("LICENSING.md", os.path.join(ROOT, "LICENSING.md")))
    out.append(("УСТАНОВКА.txt", os.path.join(HERE, "УСТАНОВКА.txt")))
    return sorted(out)


def main():
    dist = os.path.join(ROOT, "dist")
    os.makedirs(dist, exist_ok=True)
    path = os.path.join(dist, "VARKA-%s.zip" % VERSION)
    files = layout()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for arc, disk in files:
            info = zipfile.ZipInfo(arc, STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.flag_bits |= 0x800  # имена в UTF-8 (УСТАНОВКА.txt) — 7-Zip, WinRAR и Проводник читают верно
            with open(disk, "rb") as f:
                z.writestr(info, f.read())
    print("%s  (%d файлов)" % (os.path.relpath(path, ROOT), len(files)))
    for arc, _ in files:
        print("  " + arc)


if __name__ == "__main__":
    main()
