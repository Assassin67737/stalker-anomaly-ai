#!/usr/bin/env python3
"""
Материалы игры для лучей двойника (24.10.2026): gamemtl.xr (+ materials.ltx, если есть) → levels/materials.tsv.

    python3 tools/twin/vision/bake_mtl.py <gamemtl.xr> [materials.ltx]

gamemtl.xr лежит в db/files.db0 (converter.exe -unpack -xdb ../db/files.db0 -dir <папка>).
Формат — xrEngine/GameMtlLib.{h,cpp}: чанки u32 id, u32 size; GAMEMTLS_CHUNK_MTLS (0x1002) — по чанку на материал,
внутри MAIN (0x1000: ID u32, имя stringZ), FLAGS (0x1001), FACTORS (0x1003: shoot, bounce_damage, vis_transparency,
snd_occlusion). Номер треугольника cform → материал по ИНДЕКСУ в списке (GetMaterialByIdx), не по ID.
Строка tsv: индекс, ID, имя, passable, shoot_factor, vis_transparency.
Глазам (Feel_Vision.cpp): проницаемость материалов на луче перемножается, видно, пока произведение > порога.
Пуле (Level_bullet_manager_firetrace.cpp): shoot_factor 0 — летит насквозь (кусты); бронебойность ≥ shoot_factor —
пробивает, скорость × (ap − shoot)/ap; иначе застревает (или рикошет).
"""
import os
import struct
import sys

FL_PASSABLE = 1 << 7


def chunks(b, off=0, end=None):
    end = len(b) if end is None else end
    while off + 8 <= end:
        cid, size = struct.unpack_from('<II', b, off)
        yield cid & 0x7fffffff, off + 8, off + 8 + size
        off += 8 + size


def find(b, lo, hi, want):
    for cid, a, z in chunks(b, lo, hi):
        if cid == want:
            return a, z
    return None


def main():
    src = sys.argv[1]
    b = open(src, 'rb').read()
    mt = find(b, 0, len(b), 0x1002)
    rows = []
    for _, a, z in chunks(b, mt[0], mt[1]):
        m = find(b, a, z, 0x1000)
        mid = struct.unpack_from('<I', b, m[0])[0]
        name = b[m[0] + 4:b.index(b'\0', m[0] + 4)].decode('cp1251')
        fl = struct.unpack_from('<I', b, find(b, a, z, 0x1001)[0])[0]
        f = find(b, a, z, 0x1003)
        shoot, _bounce, vis, _snd = struct.unpack_from('<4f', b, f[0])
        rows.append([mid, name, int(bool(fl & FL_PASSABLE)), shoot, vis])
    if len(sys.argv) > 2 and os.path.exists(sys.argv[2]):
        print('materials.ltx — правки не применены (не реализовано)', file=sys.stderr)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'levels', 'materials.tsv')
    with open(out, 'w') as o:
        o.write('# idx\tid\tname\tpassable\tshoot_factor\tvis_transparency\n')
        for i, (mid, name, pas, shoot, vis) in enumerate(rows):
            o.write(f'{i}\t{mid}\t{name}\t{pas}\t{shoot:.4f}\t{vis:.4f}\n')
    print(f'{len(rows)} материалов → {out}')


if __name__ == '__main__':
    main()
