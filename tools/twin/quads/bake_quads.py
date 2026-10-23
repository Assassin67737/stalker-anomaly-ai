#!/usr/bin/env python3
"""
Квадранты (23.10.2026): навмеш уровня → площадки для трасс дирижёра.

  python3 quads/bake_quads.py levels/src/l03_agroprom l03_agroprom

Площадка (квадрант) = кусок навмеша внутри клетки Q×Q м, связный по ссылкам нод. Поэтому две комнаты за
стеной в одной клетке — разные площадки, этажи здания — тоже. Обрывки меньше MIN_NODES приклеиваются
к соседу, с которым больше всего ссылок. Этаж — от земли вокруг: 0 земля, выше 1, 2…, ниже −1 (тоннель, подвал).

Кто кого видит: у каждой площадки SAMPLES точки-глаза (нода у центра и самая дальняя от неё) на высоте EYE;
пары ближе RANGE проверяются лучами по level.cform (vision/rays seg, в обе стороны, как движок).
vis пары = сколько из SAMPLES² отрезков свободны.

Выход (levels/):
  <имя>_quads.json      площадки: центр, высоты, этаж, укрытость, соседи; параметры запечки
  <имя>_quads_nodes.bin на каждую ноду 8 байт: i, j (клетка картинки уровня) int16, площадка uint16 (старший бит —
                        нода на границе площадки), высота int16 в шагах 5 см (y × 20)
  <имя>_quads_vis.bin   пары: a, b uint16, vis uint8 (только vis > 0)
"""
import collections
import json
import math
import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TWIN = os.path.dirname(HERE)
sys.path.insert(0, TWIN)
from level_ai import NO_LINK, load  # noqa: E402

Q = 8.0            # м: сторона клетки
MIN_NODES = 12     # обрывок меньше — приклеить к соседу
FLOOR_GAP = 2.2    # м: разрыв по высоте между этажами в клетке
GROUND_R = 3       # клеток: где искать открытую землю вокруг
SAME_Y = 1.0       # м: соседи ближе по высоте — одна поверхность, один этаж
STOREY = 4.5       # м: высота этажа над землёй (Агропром, здание у 1_6: 5 м)
EYE = 1.6          # м над нодой
RANGE = 100.0      # м: дальше пары не проверяем
SAMPLES = 2
RAYS = os.path.join(TWIN, 'vision', 'rays')
BATCH = 3_000_000  # отрезков на один запуск rays


def main(src, name):
    meta, nodes = load(os.path.join(src, 'level.ai'))
    minx, miny, minz, maxx, maxy, maxz = meta['box']
    cell = meta['cell']
    h_img = int(round((maxz - minz) / cell)) + 1
    n = len(nodes)
    sq = [(int((d['x'] - minx) // Q), int((d['z'] - minz) // Q)) for d in nodes]

    # 1. куски внутри клетки: связность по ссылкам, не выходя из клетки
    comp = [-1] * n
    ncomp = 0
    for v in range(n):
        if comp[v] >= 0:
            continue
        comp[v] = ncomp
        stack = [v]
        while stack:
            u = stack.pop()
            for w in nodes[u]['links']:
                if w != NO_LINK and w < n and comp[w] < 0 and sq[w] == sq[u]:
                    comp[w] = ncomp
                    stack.append(w)
        ncomp += 1

    # 2. обрывки — к соседу с наибольшим числом ссылок (union-find, пока есть мелкие)
    parent = list(range(ncomp))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for _ in range(4):
        size = collections.Counter(find(c) for c in comp)
        links = collections.defaultdict(collections.Counter)
        for u in range(n):
            a = find(comp[u])
            if size[a] >= MIN_NODES:
                continue
            for w in nodes[u]['links']:
                if w != NO_LINK and w < n:
                    b = find(comp[w])
                    if b != a:
                        links[a][b] += 1
        if not links:
            break
        for a, cnt in links.items():
            b = cnt.most_common(1)[0][0]
            if find(a) != find(b):
                parent[find(a)] = find(b)

    roots = {}
    qid = [0] * n
    for u in range(n):
        r = find(comp[u])
        qid[u] = roots.setdefault(r, len(roots))
    nq = len(roots)
    if nq > 32767:
        raise SystemExit(f'площадок {nq} — не влезает в 15 бит, увеличь Q')

    # 3. свойства площадок
    members = [[] for _ in range(nq)]
    for u in range(n):
        members[qid[u]].append(u)
    quads = []
    for q, mem in enumerate(members):
        xs = [nodes[u]['x'] for u in mem]
        ys = [nodes[u]['y'] for u in mem]
        zs = [nodes[u]['z'] for u in mem]
        cx, cy, cz = sum(xs) / len(mem), sum(ys) / len(mem), sum(zs) / len(mem)
        # укрытость: средняя открытость по 4 сторонам (0 закрыто .. 15 голо) → 0..1, где 1 = закрыто
        hi = sum(min(nodes[u]['high']) for u in mem) / len(mem) / 15
        lo = sum(min(nodes[u]['low']) for u in mem) / len(mem) / 15
        # точки-глаза: нода у центра и самая дальняя от неё
        a = min(mem, key=lambda u: (nodes[u]['x'] - cx) ** 2 + (nodes[u]['z'] - cz) ** 2 + (nodes[u]['y'] - cy) ** 2)
        b = max(mem, key=lambda u: (nodes[u]['x'] - nodes[a]['x']) ** 2 + (nodes[u]['z'] - nodes[a]['z']) ** 2)
        quads.append(dict(id=q, n=len(mem), x=round(cx, 2), y=round(cy, 2), z=round(cz, 2),
                          y0=round(min(ys), 2), y1=round(max(ys), 2),
                          sq=list(sq[mem[0]]), cover_hi=round(1 - hi, 3), cover_lo=round(1 - lo, 3),
                          eye=[a, b] if SAMPLES > 1 else [a], vid=a))

    # 4. этажи от ЗЕМЛИ, а не от нижнего слоя (23.10, юзер: «этажи вверх учли, а вниз?» — над тоннелем Агропрома
    # поверхность выходила 2-м этажом). Земля клетки = медиана высоты соседних однослойных клеток (открытый
    # рельеф) в радиусе GROUND_R клеток. Слои клетки по разрывам > FLOOR_GAP; слой, ближний к земле, — 0, выше —
    # 1, 2…, ниже — −1, −2… (тоннель, подвал). Однослойная клетка — всегда 0: она и есть земля, даже на склоне.
    by_sq = collections.defaultdict(list)
    for qd in quads:
        by_sq[tuple(qd['sq'])].append(qd)
    layers = {}
    for key, lst in by_sq.items():
        lst.sort(key=lambda qd: qd['y'])
        ls, base = [[lst[0]]], lst[0]['y']
        for qd in lst[1:]:
            if qd['y'] - base > FLOOR_GAP:
                ls.append([])
                base = qd['y']
            ls[-1].append(qd)
        layers[key] = ls
    single = {k: sum(q['y'] for q in ls[0]) / len(ls[0]) for k, ls in layers.items() if len(ls) == 1}
    for (gx, gz), ls in layers.items():
        if len(ls) == 1:
            for qd in ls[0]:
                qd['floor'] = 0
            continue
        around = sorted(single[(gx + dx, gz + dz)] for dx in range(-GROUND_R, GROUND_R + 1)
                        for dz in range(-GROUND_R, GROUND_R + 1) if (gx + dx, gz + dz) in single)
        ys = [sum(q['y'] for q in l) / len(l) for l in ls]
        g = around[len(around) // 2] if around else ys[0]
        zero = min(range(len(ls)), key=lambda i: abs(ys[i] - g))
        # выше земли — по высоте (этаж ≈ STOREY м), иначе соседние клетки одного дома нумеруют по-разному
        # (в одной есть все этажи, в другой — только крыша); ниже — по порядку слоёв
        prev = 0
        for i, l in enumerate(ls):
            if i <= zero:
                f = i - zero
            else:
                f = max(prev + 1, round((ys[i] - ys[zero]) / STOREY))
            prev = f
            for qd in l:
                qd['floor'] = f
    # над головой есть другая площадка той же клетки — «под крышей»
    for lst in by_sq.values():
        top = max(qd['y'] for qd in lst)
        for qd in lst:
            qd['roof'] = qd['y'] < top - FLOOR_GAP

    # 5. соседи: ссылки нод через границу площадок (число ссылок ≈ ширина прохода в клетках)
    nb = [collections.Counter() for _ in range(nq)]
    for u in range(n):
        for w in nodes[u]['links']:
            if w != NO_LINK and w < n and qid[w] != qid[u]:
                nb[qid[u]][qid[w]] += 1
    for qd in quads:
        qd['nb'] = [[b, c] for b, c in sorted(nb[qd['id']].items())]

    # 5б. согласие этажей (23.10, скрин юзера: одна крыша — два «этажа»). Этаж считается по клетке 8×8 м, и
    # поверхность, разрезанная границей клеток, могла получить разные номера. Правило: соседние площадки на одной
    # высоте (|Δy| < SAME_Y) — один этаж. Склеиваем такие пары (кроме чистой земли — она и так 0) и даём всей
    # поверхности этаж большинства по площади. Линт печатает, сколько нарушений было и осталось.
    def conflicts():
        return sum(1 for qd in quads for b, _ in qd['nb'] if b > qd['id']
                   and abs(quads[b]['y'] - qd['y']) < SAME_Y and quads[b]['floor'] != qd['floor'])
    before = conflicts()
    up = list(range(nq))

    def root(a):
        while up[a] != a:
            up[a] = up[up[a]]
            a = up[a]
        return a
    for qd in quads:
        for b, _ in qd['nb']:
            o = quads[b]
            if abs(o['y'] - qd['y']) < SAME_Y and (o['floor'] or qd['floor']):
                up[root(b)] = root(qd['id'])
    votes = collections.defaultdict(collections.Counter)
    for qd in quads:
        votes[root(qd['id'])][qd['floor']] += qd['n']
    for qd in quads:
        qd['floor'] = votes[root(qd['id'])].most_common(1)[0][0]
    print(f'  линт этажей: соседей на одной высоте с разным этажом было {before}, стало {conflicts()}')

    # 6. кто кого видит
    grid = collections.defaultdict(list)
    G = RANGE
    for qd in quads:
        grid[(int(qd['x'] // G), int(qd['z'] // G))].append(qd['id'])
    pairs = []
    for qd in quads:
        gx, gz = int(qd['x'] // G), int(qd['z'] // G)
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for b in grid.get((gx + dx, gz + dz), ()):
                    if b <= qd['id']:
                        continue
                    o = quads[b]
                    if (o['x'] - qd['x']) ** 2 + (o['z'] - qd['z']) ** 2 <= RANGE * RANGE:
                        pairs.append((qd['id'], b))
    print(f'{name}: площадок {nq} (из {n} нод), пар для лучей {len(pairs)}')

    eye = lambda u: (nodes[u]['x'], nodes[u]['y'] + EYE, nodes[u]['z'])  # noqa: E731
    per = SAMPLES * SAMPLES
    vis = bytearray(len(pairs))
    with tempfile.TemporaryDirectory() as tmp:
        fin, fout = os.path.join(tmp, 'segs.f32'), os.path.join(tmp, 'out.u8')
        step = max(1, BATCH // per)
        for s in range(0, len(pairs), step):
            chunk = pairs[s:s + step]
            buf = bytearray()
            for a, b in chunk:
                for ea in quads[a]['eye']:
                    for eb in quads[b]['eye']:
                        buf += struct.pack('<6f', *eye(ea), *eye(eb))
            open(fin, 'wb').write(buf)
            subprocess.run([RAYS, 'seg', os.path.join(src, 'level.cform'), fin, fout], check=True,
                           stderr=subprocess.DEVNULL)
            res = open(fout, 'rb').read()
            for k in range(len(chunk)):
                vis[s + k] = sum(res[k * per:(k + 1) * per])
            print(f'  лучи: {min(s + step, len(pairs))}/{len(pairs)}', end='\r', flush=True)
    print()

    seen = collections.Counter()
    out = os.path.join(TWIN, 'levels')
    with open(os.path.join(out, name + '_quads_vis.bin'), 'wb') as f:
        for (a, b), v in zip(pairs, vis):
            if v:
                f.write(struct.pack('<HHB', a, b, v))
                seen[a] += 1
                seen[b] += 1
    for qd in quads:
        qd['sees'] = seen[qd['id']]
        del qd['eye']
    with open(os.path.join(out, name + '_quads_nodes.bin'), 'wb') as f:
        for u, d in enumerate(nodes):
            i = int(round((d['x'] - minx) / cell))
            j = h_img - 1 - int(round((d['z'] - minz) / cell))
            edge = any(w != NO_LINK and w < n and qid[w] != qid[u] for w in d['links'])
            f.write(struct.pack('<hhHh', i, j, qid[u] | (0x8000 if edge else 0), int(round(d['y'] * 20))))
    json.dump(dict(level=name, q=Q, min_nodes=MIN_NODES, floor_gap=FLOOR_GAP, eye=EYE, range=RANGE,
                   samples=SAMPLES, floor_min=min(qd['floor'] for qd in quads),
                   floor_max=max(qd['floor'] for qd in quads), quads=quads),
              open(os.path.join(out, name + '_quads.json'), 'w'), separators=(',', ':'))
    fl = collections.Counter(qd['floor'] for qd in quads)
    print(f'  этажи: {dict(sorted(fl.items()))}; видимых пар {sum(1 for v in vis if v)}')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
