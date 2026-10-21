#!/usr/bin/env python3
"""
Геометрия уровня для 3D-вьювера (21.10.2026): level.cform → levels/<имя>_mesh.bin.

  python3 bake_mesh.py <папка уровня с level.cform> <имя>

Берём геометрию коллизий (cform), а не рендер (level.geom): по ней движок пускает лучи зрения
и пули, ту же читает vision/rays.c — значит, во вьювере видно ровно то, что «видит» ИИ.
Формат cform — см. vision/rays.c.

Выход (little-endian):
  'VKM1', nverts u32, ntris u32, aabb 6×f32 (min xyz, max xyz)
  вершины nverts × 3 × u16 — доля внутри aabb (0…65535): по x ~1.4 см на Армейках, браузеру вдвое меньше
  треугольники ntris × 3 × u32
"""
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    level_dir, name = sys.argv[1], sys.argv[2]
    raw = open(os.path.join(level_dir, 'level.cform'), 'rb').read()
    ver, nv, nt = struct.unpack_from('<3I', raw, 0)
    if ver != 4:
        raise SystemExit(f'cform версии {ver}, ждём 4')
    box = np.array(struct.unpack_from('<6f', raw, 12), dtype=np.float32)
    off = 36
    verts = np.frombuffer(raw, np.float32, nv * 3, off).reshape(nv, 3)
    off += nv * 12
    tris = np.frombuffer(raw, np.uint32, nt * 4, off).reshape(nt, 4)[:, :3]   # 4-е слово — материал/сектор

    lo, hi = verts.min(0), verts.max(0)       # рамка по факту (заголовок бывает шире)
    q = np.round((verts - lo) / np.maximum(hi - lo, 1e-6) * 65535).astype('<u2')

    out = os.path.join(HERE, 'levels', f'{name}_mesh.bin')
    with open(out, 'wb') as f:
        f.write(b'VKM1' + struct.pack('<2I6f', nv, nt, *lo, *hi))
        f.write(q.tobytes())
        f.write(np.ascontiguousarray(tris, dtype='<u4').tobytes())
    print(f'{out}: {nv} вершин, {nt} треугольников, {os.path.getsize(out) / 1e6:.0f} МБ, '
          f'рамка x {lo[0]:.0f}…{hi[0]:.0f}, y {lo[1]:.0f}…{hi[1]:.0f}, z {lo[2]:.0f}…{hi[2]:.0f}')


if __name__ == '__main__':
    main()
