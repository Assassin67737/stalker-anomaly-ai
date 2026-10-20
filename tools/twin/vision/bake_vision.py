#!/usr/bin/env python3
"""
Пространственное зрение: панорама на каждую ноду навмеша (20.10.2026).

Из каждой ноды level.ai — NDIRS горизонтальных лучей по геометрии коллизий level.cform,
на двух высотах глаз: стоя и сидя. Луч — тот же, что у игры (ray_pick, статика, см. rays.c).
Ходить по уровню не нужно: геометрия лежит в файле. Прогулка в игре — сверка (varka_probe).

Выход (рядом с подложкой из bake_level.py):
  levels/<имя>_pano.bin    u16, см до упора (65535 = до RANGE пусто): сначала все ноды стоя
                           (vid × NDIRS), потом все сидя. Направление i: азимут 2π·i/NDIRS,
                           dir = (cos, 0, sin) в координатах игры (x восток, z север)
  levels/<имя>_vision.png  та же сетка, что <имя>.png (верхняя нода клетки):
                           R = замкнутость — доля направлений, где стена ближе WALL м
                           G = глубина обзора — медиана дистанции стоя, логарифм 0..RANGE → 0..255
                           B = полукрытие — доля направлений: сидя упор ближе LOW м, стоя видно дальше FAR м
                               (бруствер, подоконник, машина: присел — спрятался, встал — стреляешь)
  levels/<имя>.json        + поле vision {ndirs, range, eyes, wall, low, far}
  GAME_VISION/<имя>.bin    для игры (varka_vision.script): 3 байта на ноду по порядку vid —
                           замкнутость, глубина (лог), полукрытие; те же числа, что в каналах PNG

Использование:
  python3 vision/bake_vision.py <папка уровня с level.ai и level.cform> <имя>
"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TWIN = os.path.dirname(HERE)
sys.path.insert(0, TWIN)
from level_ai import load  # noqa: E402

NDIRS = 32
RANGE = 150.0          # м: дальше — «до горизонта»
EYES = (1.6, 1.0)      # м над нодой: стоя, сидя
WALL = 3.0             # м: упор ближе = стена рядом
LOW, FAR = 1.5, 15.0   # полукрытие: сидя упор ближе LOW, стоя видно дальше FAR

RAYS = os.path.join(HERE, 'rays')
GAME_VISION = '/mnt/games/ANOMALY_DEV/appdata/varka_vision'  # игра читает ../appdata/varka_vision/<level.name()>.bin


def ensure_rays():
    src = os.path.join(HERE, 'rays.c')
    if not os.path.exists(RAYS) or os.path.getmtime(RAYS) < os.path.getmtime(src):
        subprocess.run(['gcc', '-O3', '-march=native', '-fopenmp', '-o', RAYS, src, '-lm'], check=True)


def pano(cform, pts, eye, tmp):
    p_in = os.path.join(tmp, 'pts.f32')
    p_out = os.path.join(tmp, 'pano.u16')
    (pts + np.array([0, eye, 0], np.float32)).astype(np.float32).tofile(p_in)
    subprocess.run([RAYS, 'pano', cform, p_in, p_out, str(NDIRS), str(RANGE)], check=True)
    return np.fromfile(p_out, np.uint16).reshape(-1, NDIRS)


def bake(level_dir, name):
    ensure_rays()
    meta, nodes = load(os.path.join(level_dir, 'level.ai'))
    pts = np.array([[n['x'], n['y'], n['z']] for n in nodes], np.float32)
    cform = os.path.join(level_dir, 'level.cform')

    with tempfile.TemporaryDirectory() as tmp:
        stand = pano(cform, pts, EYES[0], tmp)
        crouch = pano(cform, pts, EYES[1], tmp)

    out = os.path.join(TWIN, 'levels')
    np.concatenate([stand, crouch]).tofile(os.path.join(out, name + '_pano.bin'))

    ds = np.where(stand == 65535, RANGE * 100, stand).astype(np.float32) / 100
    dc = np.where(crouch == 65535, RANGE * 100, crouch).astype(np.float32) / 100
    enc = (ds < WALL).mean(1)
    deep = np.median(ds, 1)
    half = ((dc < LOW) & (ds > FAR)).mean(1)

    # сетка — как в bake_level.py: пиксель = клетка, север вверх, верхняя нода клетки
    minx, miny, minz, maxx, maxy, maxz = meta['box']
    cell = meta['cell']
    w = int(round((maxx - minx) / cell)) + 1
    h = int(round((maxz - minz) / cell)) + 1
    i = np.rint((pts[:, 0] - minx) / cell).astype(int)
    j = h - 1 - np.rint((pts[:, 2] - minz) / cell).astype(int)
    order = np.argsort(pts[:, 1])  # снизу вверх: верхняя нода пишется последней и побеждает
    img = np.zeros((h, w, 4), np.uint8)
    img[j[order], i[order], 0] = np.rint(enc[order] * 255)
    img[j[order], i[order], 1] = np.rint(np.log1p(deep[order]) / np.log1p(RANGE) * 255)
    img[j[order], i[order], 2] = np.rint(half[order] * 255)
    img[j[order], i[order], 3] = 255
    Image.fromarray(img, 'RGBA').save(os.path.join(out, name + '_vision.png'))

    # для игры: по ноде, в порядке vid (Lua: string.byte(data, vid*3 + 1..3))
    per_node = np.stack([np.rint(enc * 255), np.rint(np.log1p(deep) / np.log1p(RANGE) * 255),
                         np.rint(half * 255)], 1).astype(np.uint8)
    if os.path.isdir(os.path.dirname(GAME_VISION)):
        os.makedirs(GAME_VISION, exist_ok=True)
        per_node.tofile(os.path.join(GAME_VISION, name + '.bin'))

    mpath = os.path.join(out, name + '.json')
    m = json.load(open(mpath))
    m['vision'] = dict(ndirs=NDIRS, range=RANGE, eyes=list(EYES), wall=WALL, low=LOW, far=FAR)
    json.dump(m, open(mpath, 'w'), indent=1)

    print(f'{name}: {len(pts)} нод × {NDIRS} направлений × {len(EYES)} высоты')
    print(f'  замкнутость: среднее {enc.mean():.2f}, «спина к стене» (≥ 1/4 круга) {(enc >= 0.25).mean():.1%}')
    print(f'  глубина обзора: медиана {np.median(deep):.1f} м, до горизонта {(deep >= RANGE).mean():.1%}')
    print(f'  полукрытие хоть в одну сторону: {(half > 0).mean():.1%}')


if __name__ == '__main__':
    bake(sys.argv[1], sys.argv[2])
