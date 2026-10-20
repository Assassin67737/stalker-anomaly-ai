#!/usr/bin/env python3
"""
Чтение level.ai (навмеш X-Ray, версия 10) — без движка.

Формат взят из исходника Anomaly:
  xrEngine/xrLevel.h            hdrNODES, NodeCompressed, NodePosition
  xrGame/level_graph.cpp:38     m_row_length
  xrGame/level_graph_inline.h   unpack_xz, vertex_position

Заголовок (56 байт):  version u32, count u32, cell_size f32, factor_y f32,
                      aabb (min xyz, max xyz) 6×f32, guid 16 байт
Нода (23 байта):      links 12 байт (4 ссылки по 23 бита), high cover u16 (4×4 бита),
                      low cover u16, plane u16, position 5 байт (xz 24 бита + y u16)

Использование:
  python3 level_ai.py level.ai out.png          картинка сверху
  python3 level_ai.py level.ai out.json         ноды для вьювера
"""
import json
import struct
import sys

HDR = struct.Struct('<IIff6f16s')
NODE = 23
NO_LINK = 0x7fffff  # ссылки нет = стена/край


def load(path):
    raw = open(path, 'rb').read()
    version, count, cell, factor_y, *box, _guid = HDR.unpack_from(raw, 0)
    minx, miny, minz, maxx, maxy, maxz = box
    if version != 10:
        raise SystemExit(f'level.ai версии {version}, парсер знает только 10')
    if HDR.size + count * NODE != len(raw):
        raise SystemExit(f'размер не сходится: {HDR.size}+{count}×{NODE} != {len(raw)}')

    row = int((maxz - minz) / cell + 1e-6 + 1.5)  # m_row_length
    nodes = []
    off = HDR.size
    for _ in range(count):
        d = raw[off:off + 12]
        links = (
            int.from_bytes(d[0:4], 'little') & NO_LINK,
            (int.from_bytes(d[2:6], 'little') >> 7) & NO_LINK,
            (int.from_bytes(d[5:9], 'little') >> 6) & NO_LINK,
            (int.from_bytes(d[8:12], 'little') >> 5) & NO_LINK,
        )
        high, low = struct.unpack_from('<HH', raw, off + 12)
        xz = int.from_bytes(raw[off + 18:off + 21], 'little')
        (py,) = struct.unpack_from('<H', raw, off + 21)
        nodes.append({
            'x': (xz // row) * cell + minx,
            'z': (xz % row) * cell + minz,
            'y': py / 65535 * factor_y + miny,
            'links': links,
            # открытость по 4 направлениям, 0..15 (0 = закрыто, 15 = голо; движок ищет минимум)
            'high': [(high >> s) & 15 for s in (0, 4, 8, 12)],
            'low': [(low >> s) & 15 for s in (0, 4, 8, 12)],
        })
        off += NODE
    meta = dict(version=version, count=count, cell=cell, factor_y=factor_y,
                box=[minx, miny, minz, maxx, maxy, maxz], row=row)
    return meta, nodes


def to_png(meta, nodes, out, px=2):
    from PIL import Image
    minx, miny, minz, maxx, maxy, maxz = meta['box']
    cell = meta['cell']
    w = int((maxx - minx) / cell) + 1
    h = int((maxz - minz) / cell) + 1
    img = Image.new('RGB', (w, h), (18, 20, 15))
    pix = img.load()
    span = max(maxy - miny, 1e-3)
    for n in nodes:
        i = int(round((n['x'] - minx) / cell))
        j = h - 1 - int(round((n['z'] - minz) / cell))  # север вверх
        t = (n['y'] - miny) / span                       # высота → яркость
        cover = 1 - min(sum(n['high']), sum(n['low'])) / 60  # укрытие → тёплый оттенок
        g = int(70 + 150 * t)
        pix[i, j] = (int(g * (0.6 + 0.6 * cover)), g, int(g * (0.8 - 0.4 * cover)))
    img = img.resize((w * px, h * px), Image.NEAREST)
    img.save(out)
    return w, h


if __name__ == '__main__':
    meta, nodes = load(sys.argv[1])
    print(json.dumps(meta))
    out = sys.argv[2] if len(sys.argv) > 2 else None
    if out and out.endswith('.png'):
        print('картинка', to_png(meta, nodes, out))
    elif out and out.endswith('.json'):
        json.dump({'meta': meta, 'nodes': [[round(n['x'], 2), round(n['y'], 2), round(n['z'], 2),
                                            n['links'], n['high'], n['low']] for n in nodes]},
                  open(out, 'w'), separators=(',', ':'))
        print('json', out)
