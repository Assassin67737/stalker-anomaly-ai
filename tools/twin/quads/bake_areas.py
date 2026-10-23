#!/usr/bin/env python3
"""
Аморфная авторазметка территорий (23.10.2026): водораздел по «расстоянию до стены», как Recast режет навмеш.

  python3 quads/bake_areas.py levels/src/l03_agroprom l03_agroprom

Нужна запечка квадрантов (bake_quads.py) — из неё этаж и «под крышей» каждой ноды.
Выход: levels/<имя>_areas_auto.json — тот же формат, что у ручной разметки (areas_core.js); смотреть
quads.html?areas=auto или quads3d.html?areas=auto. Сохранишь оттуда — станет ручной разметкой (черновик для правки).

Как:
  1. D — расстояние до края проходимого в шагах нод (0.7 м): поиск в ширину по ссылкам от нод, у которых
     не все 4 ссылки (стена, обрыв, край). Середина двора — вершина, дверь и пролом — узкий перевал.
  2. Заливка сверху вниз (ноды по убыванию D): нода без размеченных соседей — новая область с вершиной D;
     сосед один — к нему; соседей из разных областей несколько — это перевал между ними (запоминаем его высоту).
  3. Слияние: две области сливаются, если перевал между ними почти как меньшая вершина (MERGE_K) — значит, узкого
     места нет, это одно пространство, порезанное шумом рельефа. Узкий перевал (дверь) — граница остаётся.
  4. Крошки (< MIN_NODES) — к соседу с самой длинной общей границей.
  5. Категория по форме и месту: ниже земли — подземное; над землёй — высота / комната (под крышей);
     узкое и вытянутое — коридор; под крышей на земле — комната; широкое и большое — открытое; прочее — двор.
"""
import collections
import json
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TWIN = os.path.dirname(HERE)
sys.path.insert(0, TWIN)
from level_ai import NO_LINK, load  # noqa: E402

MERGE_K = 0.72     # перевал ≥ этой доли меньшей вершины — одна область
MERGE_ABS = 2      # или вершина выше перевала меньше чем на столько шагов — шум
MIN_NODES = 60     # ≈ 30 м²: меньше — приклеить к соседу
MAX_NODES = 2500   # ≈ 1200 м²: больше — не сливать (поле не должно стать одной областью на полкарты)


def main(src, name):
    meta, nodes = load(os.path.join(src, 'level.ai'))
    n = len(nodes)
    Q = json.load(open(os.path.join(TWIN, 'levels', name + '_quads.json')))['quads']
    raw = open(os.path.join(TWIN, 'levels', name + '_quads_nodes.bin'), 'rb').read()
    st = 8 if len(raw) == n * 8 else 6
    qid = [struct.unpack_from('<H', raw, k * st + 4)[0] & 0x7fff for k in range(n)]
    links = [[w for w in d['links'] if w != NO_LINK and w < n] for d in nodes]

    # 1. расстояние до края
    D = [-1] * n
    queue = collections.deque()
    for k in range(n):
        if len(links[k]) < 4:
            D[k] = 0
            queue.append(k)
    while queue:
        u = queue.popleft()
        for w in links[u]:
            if D[w] < 0:
                D[w] = D[u] + 1
                queue.append(w)
    D = [d if d >= 0 else 0 for d in D]
    # чуть сгладить — плато дают ложные вершины
    Ds = [(2 * D[k] + sum(D[w] for w in links[k])) / (2 + len(links[k])) for k in range(n)]

    # 2. заливка сверху вниз
    order = sorted(range(n), key=lambda k: -Ds[k])
    lab = [-1] * n
    peak = []
    saddle = {}   # (a, b) → высота перевала (наибольшая из встреченных)
    for k in order:
        ls = {lab[w] for w in links[k] if lab[w] >= 0}
        if not ls:
            lab[k] = len(peak)
            peak.append(Ds[k])
            continue
        best = max(ls, key=lambda a: peak[a])
        lab[k] = best
        for a in ls:
            if a != best:
                key = (min(a, best), max(a, best))
                saddle[key] = max(saddle.get(key, -1), Ds[k])
    nreg = len(peak)

    # 3. слияние по перевалам (от высоких перевалов к низким)
    up = list(range(nreg))
    size = collections.Counter(lab)
    top = peak[:]

    def root(a):
        while up[a] != a:
            up[a] = up[up[a]]
            a = up[a]
        return a
    for (a, b), s in sorted(saddle.items(), key=lambda kv: -kv[1]):
        ra, rb = root(a), root(b)
        if ra == rb:
            continue
        lo = min(top[ra], top[rb])
        if (s >= MERGE_K * lo or lo - s < MERGE_ABS) and size[ra] + size[rb] <= MAX_NODES:
            up[rb] = ra
            top[ra] = max(top[ra], top[rb])
            size[ra] += size[rb]
    lab = [root(a) for a in lab]

    # 4. крошки — к соседу с самой длинной общей границей
    for _ in range(6):
        size = collections.Counter(lab)
        border = collections.defaultdict(collections.Counter)
        for k in range(n):
            if size[lab[k]] >= MIN_NODES:
                continue
            for w in links[k]:
                if lab[w] != lab[k]:
                    border[lab[k]][lab[w]] += 1
        if not border:
            break
        remap = {a: c.most_common(1)[0][0] for a, c in border.items()}
        changed = False
        for k in range(n):
            if lab[k] in remap and size[lab[k]] < MIN_NODES:
                lab[k] = remap[lab[k]]
                changed = True
        if not changed:
            break

    # 5. категории
    regs = collections.defaultdict(list)
    for k in range(n):
        regs[lab[k]].append(k)
    areas = []
    for i, (r, ks) in enumerate(sorted(regs.items(), key=lambda kv: -len(kv[1]))):
        xs = [nodes[k]['x'] for k in ks]
        zs = [nodes[k]['z'] for k in ks]
        ys = [nodes[k]['y'] for k in ks]
        floors = collections.Counter(Q[qid[k]]['floor'] for k in ks)
        fl = floors.most_common(1)[0][0]
        roof = sum(1 for k in ks if Q[qid[k]]['roof']) / len(ks)
        width = 2 * sum(D[k] for k in ks) / len(ks) * meta['cell']              # средняя «ширина», м
        span = math.hypot(max(xs) - min(xs), max(zs) - min(zs))                 # размах, м
        area = len(ks) * meta['cell'] ** 2
        if fl < 0:
            cat = 'under'
        elif max(ys) - min(ys) > 2.5 and area < 150:
            cat = 'stairs'
        elif fl > 0:
            cat = 'room' if roof > 0.5 else 'height'
        elif width < 3.0 and span > 4 * max(width, 1):
            cat = 'corridor'
        elif roof > 0.5:
            cat = 'room'
        elif area > 500 and width > 8:
            cat = 'open'
        else:
            cat = 'yard'
        ks.sort()
        rle = []
        for k in ks:
            if rle and rle[-1][0] + rle[-1][1] == k:
                rle[-1][1] += 1
            else:
                rle.append([k, 1])
        areas.append({'id': i + 1, 'name': f'А{i + 1}', 'cat': cat, 'locked': False,
                      'note': f'авто: ~{area:.0f} м², ширина ~{width:.1f} м, размах {span:.0f} м', 'nodes': rle})

    out = os.path.join(TWIN, 'levels', name + '_areas_auto.json')
    json.dump({'level': name, 'version': 1, 'savedAt': 0, 'nextId': len(areas) + 1, 'auto': True,
               'areas': areas, 'lines': [], 'points': []}, open(out, 'w'), separators=(',', ':'))
    cats = collections.Counter(a['cat'] for a in areas)
    print(f'{name}: вершин {nreg} → областей {len(areas)}; по категориям: {dict(cats.most_common())}')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
