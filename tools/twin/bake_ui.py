#!/usr/bin/env python3
"""
Нашивки группировок для вьювера (21.10.2026): атлас игры → assets/factions/<группировка>.png.

Берём нашивки из меню новой игры Anomaly (ui_mm_faction_patches, 64×64 каждая): те же эмблемы,
что игрок видит, выбирая группировку. Это арт игры — в репозиторий не кладём (assets/ в .gitignore),
каждый запекает из своей установки.

  1. распаковать UI-текстуры игры конвертером (как уровни):
       wine converter.exe -unpack -xdb <ANOMALY>/db/textures/textures_ui.db0 -dir ./out_ui
  2. python3 bake_ui.py out_ui/textures/ui/ui_mm_faction_patches.dds

Где какая нашивка в атласе — из описания текстур игры (configs/ui/textures_descr/ui_mm_faction_patches.xml).
"""
import os
import re
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DESCR = '/mnt/games/ANOMALY_DEV/tools/_unpacked/configs/ui/textures_descr/ui_mm_faction_patches.xml'


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    atlas = Image.open(sys.argv[1]).convert('RGBA')
    out = os.path.join(HERE, 'assets', 'factions')
    os.makedirs(out, exist_ok=True)
    names = []
    for m in re.finditer(r'id="ui_mm_faction_(\w+?)"\s+x="(\d+)"\s+y="(\d+)"\s+width="(\d+)"\s+height="(\d+)"',
                         open(DESCR, encoding='latin-1').read()):
        name, x, y, w, h = m.group(1), *map(int, m.groups()[1:])
        if name.endswith('_inactive'):
            continue
        atlas.crop((x, y, x + w, y + h)).save(os.path.join(out, name + '.png'))
        names.append(name)
    print(f'нашивок: {len(names)} → {os.path.relpath(out, HERE)}: {", ".join(names)}')


if __name__ == '__main__':
    main()
