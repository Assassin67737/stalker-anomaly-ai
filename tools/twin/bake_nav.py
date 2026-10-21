#!/usr/bin/env python3
"""
Навмеш для двойника (21.10.2026): level.ai → levels/<имя>_nav.bin, читается из LuaJIT (sim/nav.lua).

  python3 bake_nav.py <папка уровня с level.ai> <имя>

Выход (little-endian), массивы подряд, без выравнивания:
  'VKN1', count u32, cell f32, box 6×f32, row u32
  pos   count × 3 × f32      x, y, z ноды
  links count × 4 × i32      соседи по направлениям 0..3 (−1 = стена/край); направления как в движке
  cover count × 8 × u8       открытость high[4], low[4] по тем же направлениям (0 закрыто … 15 голо)
"""
import os
import struct
import sys

import numpy as np

from level_ai import NO_LINK, load

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    level_dir, name = sys.argv[1], sys.argv[2]
    meta, nodes = load(os.path.join(level_dir, 'level.ai'))
    n = len(nodes)
    pos = np.array([(v['x'], v['y'], v['z']) for v in nodes], dtype='<f4')
    links = np.array([[-1 if l == NO_LINK else l for l in v['links']] for v in nodes], dtype='<i4')
    cover = np.array([v['high'] + v['low'] for v in nodes], dtype='u1')

    # направления ссылок — проверяем, а не верим: среднее смещение к соседу по каждому из 4 направлений
    for d in range(4):
        ok = links[:, d] >= 0
        delta = pos[links[ok, d]] - pos[ok]
        print(f'  ссылка {d}: dx {delta[:, 0].mean():+.2f}, dz {delta[:, 2].mean():+.2f}  ({ok.sum()} нод)')

    out = os.path.join(HERE, 'levels', f'{name}_nav.bin')
    with open(out, 'wb') as f:
        f.write(b'VKN1' + struct.pack('<If6fI', n, meta['cell'], *meta['box'], meta['row']))
        f.write(pos.tobytes())
        f.write(links.tobytes())
        f.write(cover.tobytes())
    print(f'{out}: {n} нод, клетка {meta["cell"]} м, {os.path.getsize(out) / 1e6:.1f} МБ')


if __name__ == '__main__':
    main()
