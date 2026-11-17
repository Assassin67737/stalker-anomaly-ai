#!/usr/bin/env python3
"""
Голос (17.11.2026): скелет акустики уровня для varka_voice — комнаты и проёмы из квадрантов.

  python3 voice/bake_voice.py l07_military [папка_levels] [папка_выхода]

Звук запекать целиком не надо: кто кричит, решается в бою, крик — редкое событие. Запекается только
топология: площадки (куски навмеша 8×8 м, связные по ссылкам нод — две комнаты за стеной разные, этажи тоже)
и кто с кем соседствует. Путь звука в обход стены считает игра в момент крика (Дейкстра по ~сотне площадок).

Вход: levels/<имя>_quads.json, <имя>_quads_nodes.bin (quads/bake_quads.py).
Выход: <выход>/<имя>.bin, little-endian:
  "VOX1", u16 nq
  nq раз: i16 x, i16 y, i16 z (дм), u8 nnb, nnb × u16 сосед
  u32 nv, nv × u16 площадка ноды (по порядку vid; 65535 — нет)
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TWIN = os.path.dirname(HERE)


def dm(v):
    x = int(round(v * 10))
    if not -32768 <= x <= 32767:
        raise SystemExit(f'координата {v} не лезет в i16 дм')
    return x


def main(name, levels, out):
    q = json.load(open(os.path.join(levels, name + '_quads.json')))
    quads = q['quads']
    raw = open(os.path.join(levels, name + '_quads_nodes.bin'), 'rb').read()
    nv = len(raw) // 8
    buf = bytearray(b'VOX1')
    buf += struct.pack('<H', len(quads))
    for k, d in enumerate(quads):
        assert d['id'] == k
        nb = [n for n, _ in d['nb']][:255]
        buf += struct.pack('<hhhB', dm(d['x']), dm(d['y']), dm(d['z']), len(nb))
        buf += struct.pack(f'<{len(nb)}H', *nb)
    buf += struct.pack('<I', nv)
    vq = bytearray(nv * 2)
    for v in range(nv):
        _, _, qd, _ = struct.unpack_from('<hhHh', raw, v * 8)
        qd &= 0x7FFF
        struct.pack_into('<H', vq, v * 2, qd if qd < len(quads) else 65535)
    buf += vq
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, name + '.bin')
    open(path, 'wb').write(buf)
    nbs = sum(len(d['nb']) for d in quads)
    print(f'{name}: {len(quads)} площадок, {nbs} соседств, {nv} нод → {path} ({len(buf) // 1024} КБ)')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    lv = sys.argv[2] if len(sys.argv) > 2 else os.path.join(TWIN, 'levels')
    od = sys.argv[3] if len(sys.argv) > 3 else '/mnt/games/ANOMALY_DEV/appdata/varka_voice'
    main(sys.argv[1], lv, od)
