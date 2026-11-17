#!/usr/bin/env python3
"""
Заглушение звука стенами для движка (17.11.2026): level.cform + gamemtl.xr → gamedata/levels/<имя>/level.som.

  python3 voice/bake_som.py <gamemtl.xr> <имя> [папка_src] [gamedata]
  python3 voice/bake_som.py <gamemtl.xr> all

Зачем. Движок глушит звук стенами ТОЛЬКО по level.som (xrSound/SoundRender_Core_Processor.cpp):
  - уши NPC: сила = (1 − d/радиус) × громкость × Π occ по треугольникам на отрезке ухо→звук (IGame_Level.cpp:305);
  - уши игрока: громкость эмиттера × тот же Π occ (get_occlusion; вторая модель geom_MODEL в Anomaly выключена —
    set_geometry_occ закомментирован, xrCDB/xr_area.cpp:139).
В уровнях Anomaly level.som нет → звук везде шар сквозь стены. Файл кладётся в gamedata, движок не трогаем.

Что внутри. Статическая геометрия уровня (cform), каждый треугольник со своим occ = snd_occlusion материала
из gamemtl.xr (коэффициенты GSC: кирпич 0.45, бетон 0.6, штукатурка 0.75, металл 0, земля 0 …).
Выкинуто: проходимые материалы (кусты, вода, fake), рабица и всё с occ ≥ 0.95, стволы деревьев (звук огибает),
треугольники меньше MIN_AREA (мелочь предметов: 99 % площади стен остаётся при четверти треугольников).
Пол MIN_OCC: GSC-ный 0 (металл, земля) глушил бы насмерть — выстрел за холмом не слышен совсем; огибание
не моделируется, поэтому каждая поверхность пропускает не меньше MIN_OCC (шов, ручка).
Луч движка отсекает задние грани (OPT_CULL): стена-коробка считается один раз, холм — один раз.

Формат (SoundRender_Core.cpp set_geometry_som): чанк 0 — u32 версия 0; чанк 1 — SOM_poly × N:
  v1, v2, v3 (9 × f32), b2sided u32, occ f32.
"""
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'vision'))
from bake_mtl import FL_PASSABLE, chunks, find  # noqa: E402

MIN_AREA = 0.05     # м²: меньше — деталь предмета, звук огибает
MIN_OCC = 0.4       # каждая поверхность пропускает не меньше (огибания нет); 17.11: 0.2 → 0.4 — выстрел за зданием в 100 м снова слышен
SKIP_OCC = 0.95     # материал почти прозрачен для звука — не писать
SKIP_NAMES = {'materials\\tree_trunk'}
DEFAULT = 'default'


def materials(path):
    g = open(path, 'rb').read()
    mt = find(g, 0, len(g), 0x1002)
    out = {}
    for _, a, z in chunks(g, mt[0], mt[1]):
        m = find(g, a, z, 0x1000)
        mid = struct.unpack_from('<I', g, m[0])[0]
        name = g[m[0] + 4:g.index(b'\0', m[0] + 4)].decode('cp1251')
        fl = struct.unpack_from('<I', g, find(g, a, z, 0x1001)[0])[0]
        snd = struct.unpack_from('<4f', g, find(g, a, z, 0x1003)[0])[3]
        out[mid] = (name, bool(fl & FL_PASSABLE), snd)
    return out


def bake(mtl, src, name, gamedata):
    b = open(os.path.join(src, 'level.cform'), 'rb').read()
    ver, nv, nt = struct.unpack_from('<3I', b, 0)
    assert ver == 4, ver
    V = np.frombuffer(b, dtype='<f4', count=nv * 3, offset=36).reshape(nv, 3)
    T = np.frombuffer(b, dtype='<u4', count=nt * 4, offset=36 + nv * 12).reshape(nt, 4)
    mid = (T[:, 3] & 0x3FFF).astype(np.int64)
    dflt = next(v for v in mtl.values() if v[0] == DEFAULT)
    lut = np.full(int(mid.max()) + 1, -1.0, dtype=np.float32)   # occ по ID, −1 — не писать
    for i in np.unique(mid):
        nm, ps, snd = mtl.get(int(i), dflt)
        if not (ps or snd >= SKIP_OCC or nm in SKIP_NAMES):
            lut[i] = max(snd, MIN_OCC)
    occ = lut[mid]
    a, c1, c2 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(c1 - a, c2 - a), axis=1)
    keep = (occ >= 0) & (area >= MIN_AREA)
    n = int(keep.sum())
    poly = np.zeros(n, dtype=[('v', '<f4', 9), ('b2', '<u4'), ('occ', '<f4')])
    poly['v'] = np.hstack([a[keep], c1[keep], c2[keep]])
    poly['occ'] = occ[keep]
    body = poly.tobytes()
    out = os.path.join(gamedata, 'levels', name)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'level.som'), 'wb') as f:
        f.write(struct.pack('<III', 0, 4, 0))          # чанк 0: версия
        f.write(struct.pack('<II', 1, len(body)))       # чанк 1: полигоны
        f.write(body)
    print(f'{name}: {n} из {nt} треугольников, {len(body) / 1e6:.1f} МБ')


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    mtl = materials(sys.argv[1])
    src_root = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(HERE), 'levels', 'src')
    gamedata = sys.argv[4] if len(sys.argv) > 4 else '/mnt/games/ANOMALY_DEV/gamedata'
    names = sorted(os.listdir(src_root)) if sys.argv[2] == 'all' else [sys.argv[2]]
    for nm in names:
        src = os.path.join(src_root, nm)
        if os.path.exists(os.path.join(src, 'level.cform')):
            bake(mtl, src, nm, gamedata)


if __name__ == '__main__':
    main()
