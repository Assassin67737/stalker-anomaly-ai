#!/usr/bin/env python3
"""
Запекание level.ai в подложку для вьювера (tools/twin/viewer.html).

Сетка навмеша = картинка: один пиксель на клетку 0,7 м, север вверх.
  levels/<имя>.png      R = высота (0..255 в рамке уровня), G = открытость стоя (high), B = сидя (low)
                        (среднее по 4 направлениям, 0..15 → 0..255; 0 = закрыто, 15 = голо), A = 255 там, где есть нода
  levels/<имя>_vid.png  RGB = vid + 1 (0 = ноды нет) — по нему вьювер узнаёт ноду под мышью
  levels/<имя>.json     рамка уровня, размер клетки, число нод

Если над одной клеткой несколько нод (этажи, мосты) — берём верхнюю: вид сверху.

Использование:
  python3 bake_level.py путь/к/level.ai l07_military
"""
import json
import os
import sys

from PIL import Image

from level_ai import load

HERE = os.path.dirname(os.path.abspath(__file__))


def bake(path, name):
    meta, nodes = load(path)
    minx, miny, minz, maxx, maxy, maxz = meta['box']
    cell = meta['cell']
    w = int(round((maxx - minx) / cell)) + 1
    h = int(round((maxz - minz) / cell)) + 1
    span = max(maxy - miny, 1e-3)

    info = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    vids = Image.new('RGB', (w, h), (0, 0, 0))
    pi, pv = info.load(), vids.load()
    top = {}  # (i, j) → y верхней ноды

    for vid, n in enumerate(nodes):
        i = int(round((n['x'] - minx) / cell))
        j = h - 1 - int(round((n['z'] - minz) / cell))  # север вверх
        if top.get((i, j), -1e9) >= n['y']:
            continue
        top[(i, j)] = n['y']
        pi[i, j] = (int(255 * (n['y'] - miny) / span),
                    sum(n['high']) * 17 // 4,
                    sum(n['low']) * 17 // 4,
                    255)
        k = vid + 1
        pv[i, j] = (k >> 16 & 255, k >> 8 & 255, k & 255)

    out = os.path.join(HERE, 'levels')
    os.makedirs(out, exist_ok=True)
    info.save(os.path.join(out, name + '.png'))
    vids.save(os.path.join(out, name + '_vid.png'))
    json.dump(dict(name=name, count=meta['count'], cell=cell, box=meta['box'], w=w, h=h,
                   stacked=meta['count'] - len(top)),
              open(os.path.join(out, name + '.json'), 'w'), indent=1)

    # список уровней — вьювер по нему угадывает, где шёл бой
    index = sorted(f[:-5] for f in os.listdir(out) if f.endswith('.json') and f != 'index.json')
    json.dump(index, open(os.path.join(out, 'index.json'), 'w'))
    print(f'{name}: {meta["count"]} нод, картинка {w}×{h}, под верхними спрятано {meta["count"] - len(top)}')


if __name__ == '__main__':
    bake(sys.argv[1], sys.argv[2])
