#!/usr/bin/env python3
"""
Дирижёр квадрантов (23.10.2026): ведёт бойцов матча по трассам из площадок и говорит, куда смотреть.

  python3 match/conductor.py                 обе стороны каждого матча (запускать рядом с run.py)
  python3 match/conductor.py --side A        только сторона A (B — как было: дирижёр игры и ваниль)

Нужно: server.py, игра с varka_cmd (команда qmove), запечка квадрантов уровня (quads/bake_quads.py).

Что делает раз в TICK секунд для каждого живого бойца, пока у него нет боя (в бою мягкий приказ сам уступает ванили):
  знание стороны   где был враг, когда его видел кто-то из своих (bsee) — свежесть SEEN_S; до первого контакта —
                   «первая догадка»: вероятная угроза с той стороны точки, что напротив наших (кругом PROB_R)
  цель             своя площадка у точки на каждого: укрытая, не под взглядом угрозы (разные бойцы — разные)
  трасса           Дейкстра по площадкам: длина × (1 + K × угроза) + LANE за площадку чужой трассы — расходятся
  шаг              площадка трассы ~STEP_M вперёд → qmove; пришёл — следующий
  темп             далеко и не под взглядом — бегом; под взглядом — сосредоточенный шаг; рядом с известным врагом — гусиным
  взгляд           площадка, которую стоит проверить: видна с шага, давно не проверена своими, есть где спрятаться,
                   ближе к угрозе; свои делят сектора (одну площадку двоим не даём)
Проверенным площадка считается, когда её видно с площадки кого-то из своих (CHECK_VIS лучей из 4) — на CHECK_S.
В trace игра пишет qmove (трасса, взгляд, темп) — вьювер рисует.
"""
import argparse
import collections
import heapq
import json
import math
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TWIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import run  # noqa: E402  (Game — тот же протокол, что у раннера)

TICK = 1.0        # с между пересчётами
REPLAN_S = 2.5    # с: один боец не чаще
STEP_M = 12.0     # м: длина шага трассы
K = 6.0           # вес угрозы в цене пути
LANE = 0.6        # прибавка к цене за площадку, занятую трассой своего
SEEN_S = 30.0     # с: сколько помнить, где видели врага
PROB_R = 35.0     # м: круг первой догадки
CHECK_VIS = 2     # из 4 лучей — «видно»
CHECK_S = 12.0    # с: проверенная площадка снова интересна через столько
LOOK_R = 70.0     # м: дальше не смотрим
GOAL_R = 18.0     # м: цели бойцов — площадки в этом радиусе от точки
COMBAT_AIDS = {89, 91, 18803, 188118, 188112, 188113, 1346, 188212}  # бой, опасность, свои-на-линии, добивание, рывок


class Quads:
    def __init__(self, name):
        Q = json.load(open(os.path.join(TWIN, 'levels', name + '_quads.json')))
        self.q = Q['quads']
        self.per = Q['samples'] ** 2
        self.vis = collections.defaultdict(dict)
        raw = open(os.path.join(TWIN, 'levels', name + '_quads_vis.bin'), 'rb').read()
        for a, b, v in struct.iter_unpack('<HHB', raw):
            self.vis[a][b] = v
            self.vis[b][a] = v
        # поиск площадки по точке: решётка 8 м
        self.grid = collections.defaultdict(list)
        for d in self.q:
            self.grid[(int(d['x'] // 8), int(d['z'] // 8))].append(d['id'])

    def at(self, x, y, z):
        """Площадка под точкой: ближайшая по плоскости с учётом высоты (этажи)."""
        gx, gz = int(x // 8), int(z // 8)
        best, bd = None, 1e9
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for q in self.grid.get((gx + dx, gz + dz), ()):
                    d = self.q[q]
                    s = math.hypot(d['x'] - x, d['z'] - z) + 3 * abs(d['y'] - y)
                    if s < bd:
                        best, bd = q, s
        return best

    def dist(self, a, b):
        p, q = self.q[a], self.q[b]
        return math.hypot(p['x'] - q['x'], p['y'] - q['y'], p['z'] - q['z'])

    def exposure(self, sources):
        """Угроза площадок 0…1 от источников [(площадка, вес)] — как quadsExposure во вьювере."""
        e = collections.defaultdict(float)
        for s, w in sources:
            e[s] = max(e[s], w)
            ys = self.q[s]['y']
            for q, v in self.vis[s].items():
                up = min(1, max(0, ys - self.q[q]['y']) / 8)
                val = min(1, w * v / self.per * (1 + up) * (1 - 0.3 * self.q[q]['cover_hi']))
                if val > e[q]:
                    e[q] = val
        return e

    def route(self, a, b, expo, busy):
        dist, prev, heap = {a: 0.0}, {}, [(0.0, a)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist.get(u, 1e18):
                continue
            if u == b:
                break
            for v, _ in self.q[u]['nb']:
                nd = d + self.dist(u, v) * (1 + K * expo.get(v, 0)) + LANE * busy.get(v, 0)
                if nd < dist.get(v, 1e18):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(heap, (nd, v))
        if b not in dist:
            return None
        path = [b]
        while path[-1] != a:
            path.append(prev[path[-1]])
        return path[::-1]


class Conductor:
    def __init__(self, game, sides):
        self.g, self.sides = game, sides
        self.Q = None
        self.level = None
        self.match = None          # match_start
        self.npc = {}              # id → последний npc_pos
        self.dead = set()
        self.seen = {}             # сторона → {враг: (x, y, z, t)}
        self.checked = {}          # сторона → {площадка: t}
        self.plan = {}             # боец → {'t', 'goal', 'path', 'wp', 'look'}
        self.start = {}            # сторона → (x, z) — где стояли в начале

    # ---------- trace ----------
    def feed(self, e):
        ev = e.get('ev')
        if ev == 'level':
            self.load(e['name'])
        elif ev == 'match_start':
            self.match = e
            if e.get('level'):
                self.load(e['level'])
            self.npc, self.dead, self.plan, self.start = {}, set(), {}, {}
            self.seen = {'A': {}, 'B': {}}
            self.checked = {'A': {}, 'B': {}}
            print(f"матч {e.get('id')}: точка ({e['zx']:.0f}, {e['zz']:.0f})")
        elif ev == 'match_end':
            print(f"  конец: {e.get('reason')}")
            self.match = None
        elif ev == 'death':
            self.dead.add(e.get('npc'))
        elif ev == 'npc_pos' and self.match:
            self.npc[e['npc']] = e
            s = self.side(e['sq'])
            if s and s not in self.start:
                mates = [n for n in self.npc.values() if self.side(n['sq']) == s]
                self.start[s] = (sum(n['px'] for n in mates) / len(mates), sum(n['pz'] for n in mates) / len(mates))
            # видел врага — сторона знает, где он был в этот миг (его позиция из его же записи)
            if s and e.get('bsee') == 1 and e.get('be', -1) in self.npc:
                o = self.npc[e['be']]
                self.seen[s][e['be']] = (o['px'], o['py'], o['pz'], time.time())

    def load(self, name):
        if name == self.level:
            return
        path = os.path.join(TWIN, 'levels', name + '_quads.json')
        if not os.path.exists(path):
            print(f'  нет запечки квадрантов {name} — python3 quads/bake_quads.py levels/src/{name} {name}')
            self.Q, self.level = None, name
            return
        t = time.time()
        self.Q, self.level = Quads(name), name
        print(f'  квадранты {name}: {len(self.Q.q)} площадок ({time.time() - t:.1f} с)')

    def side(self, sq):
        m = self.match
        if not m:
            return None
        if str(sq) in str(m['a']).split(','):
            return 'A'
        if str(sq) in str(m['b']).split(','):
            return 'B'
        return None

    # ---------- решения ----------
    def threats(self, s):
        """Источники угрозы стороны: где видели врагов; до контакта — первая догадка напротив."""
        now, Q, out = time.time(), self.Q, []
        for x, y, z, t in self.seen[s].values():
            age = now - t
            if age < SEEN_S:
                out.append((Q.at(x, y, z), 1 - 0.6 * age / SEEN_S))
        if not out and s in self.start:
            zx, zz = self.match['zx'], self.match['zz']
            sx, sz = self.start[s]
            n = math.hypot(zx - sx, zz - sz) or 1
            gx, gz = zx + (zx - sx) / n * 25, zz + (zz - sz) / n * 25    # за точкой, с той стороны
            for d in Q.q:
                r = math.hypot(d['x'] - gx, d['z'] - gz)
                if r <= PROB_R and d['floor'] == 0:
                    out.append((d['id'], 0.5 * (1 - 0.5 * r / PROB_R)))
        return out

    def goals(self, s, members, expo):
        """Каждому своя площадка у точки: укрытая и не под взглядом; ближнему — ближняя."""
        Q, zx, zz = self.Q, self.match['zx'], self.match['zz']
        cand = [d for d in Q.q if math.hypot(d['x'] - zx, d['z'] - zz) <= GOAL_R]
        cand.sort(key=lambda d: expo.get(d['id'], 0) * 2 - d['cover_hi'])
        out, used = {}, set()
        for n in sorted(members, key=lambda n: math.hypot(n['px'] - zx, n['pz'] - zz)):
            for d in cand:
                if d['id'] not in used:
                    out[n['npc']] = d['id']
                    used.add(d['id'])
                    break
        return out

    def tick(self):
        if not (self.match and self.Q):
            return
        now = time.time()
        for s in self.sides:
            members = [n for n in self.npc.values() if self.side(n['sq']) == s
                       and n['npc'] not in self.dead and n.get('hp', 1) > 0 and now - n.get('_rx', now) < 3]
            if not members:
                continue
            Q = self.Q
            here = {n['npc']: Q.at(n['px'], n['py'], n['pz']) for n in members}
            # своими глазами: что видно с площадок бойцов — проверено
            for q in here.values():
                self.checked[s][q] = now
                for o, v in Q.vis[q].items():
                    if v >= CHECK_VIS:
                        self.checked[s][o] = now
            src = self.threats(s)
            expo = Q.exposure(src)
            near_enemy = {q for q, w in src if w > 0.6}
            goals = self.goals(s, members, expo)
            busy, looks = collections.Counter(), set()
            for p in self.plan.values():
                for q in p.get('path', [])[1:]:
                    busy[q] += 1
            for n in members:
                nid = n['npc']
                if n.get('aid') in COMBAT_AIDS or n.get('bsee') == 1:
                    continue        # бой — ванили
                p = self.plan.get(nid)
                if p and now - p['t'] < REPLAN_S:
                    continue
                a, b = here[nid], goals.get(nid)
                if a is None or b is None:
                    continue
                path = Q.route(a, b, expo, busy) or [a]
                for q in path[1:]:
                    busy[q] += 1
                # шаг: площадка трассы ~STEP_M вперёд по пути
                wp, acc = path[-1], 0.0
                for i in range(1, len(path)):
                    acc += Q.dist(path[i - 1], path[i])
                    if acc >= STEP_M:
                        wp = path[i]
                        break
                look = self.look_at(s, wp, path, src, looks)
                looks.add(look)
                ahead = path[:path.index(wp) + 2] if wp in path else path
                hot = max((expo.get(q, 0) for q in ahead), default=0)
                close = any(Q.dist(a, t) < 30 for t in near_enemy)
                pace = 'sneak' if close else 'walk' if hot > 0.25 else 'run'
                d, L = Q.q[wp], Q.q[look]
                self.g.send('qmove', nid, d['vid'], round(L['x'], 1), round(L['y'] + 1.0, 1), round(L['z'], 1), pace,
                            '.'.join(map(str, path[:16])))
                self.plan[nid] = {'t': now, 'goal': b, 'path': path, 'wp': wp, 'look': look}

    def look_at(self, s, wp, path, src, taken):
        """Куда смотреть с шага wp: площадка, которую стоит проверить."""
        Q, now = self.Q, time.time()
        w = Q.q[wp]
        threat = {q for q, _ in src}
        tx = ty = 0.0
        if src:   # направление на угрозу
            tx = sum(Q.q[q]['x'] for q, _ in src) / len(src) - w['x']
            ty = sum(Q.q[q]['z'] for q, _ in src) / len(src) - w['z']
            n = math.hypot(tx, ty) or 1
            tx, ty = tx / n, ty / n
        best, bs = None, -1e9
        for q, v in Q.vis[wp].items():
            if v < CHECK_VIS or q in taken:
                continue
            d = Q.q[q]
            r = math.hypot(d['x'] - w['x'], d['z'] - w['z'])
            if r < 6 or r > LOOK_R:
                continue
            age = now - self.checked[s].get(q, 0)
            fresh = min(1.0, age / CHECK_S)                  # давно не видели — интереснее
            toward = ((d['x'] - w['x']) * tx + (d['z'] - w['z']) * ty) / r if src else 0
            score = fresh * (0.5 + d['cover_hi']) * (1 + toward) / (1 + r / 40) + (2 if q in threat else 0)
            if score > bs:
                best, bs = q, score
        if best is None:   # смотреть некуда — вперёд по трассе
            i = path.index(wp) if wp in path else 0
            best = path[min(len(path) - 1, i + 2)]
        return best


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--side', choices=['A', 'B', 'AB'], default='AB')
    args = ap.parse_args()
    g = run.Game()
    c = Conductor(g, list(args.side))
    # уровень — из начала trace (событие level), дальше — из match_start
    try:
        for line in open(run.TRACE, encoding='utf-8', errors='replace'):
            if '"level"' in line:
                e = json.loads(line)
                if e.get('ev') == 'level':
                    c.load(e['name'])
    except (OSError, ValueError):
        pass
    print(f'дирижёр квадрантов: стороны {args.side}, жду матча…')
    last = 0.0
    while True:
        for e in g.read():
            e['_rx'] = time.time()
            c.feed(e)
        if time.time() - last >= TICK:
            last = time.time()
            try:
                c.tick()
            except Exception as ex:   # игра не ответила на команду и т.п. — не падать посреди серии
                print('  тик:', ex)
        time.sleep(0.2)


if __name__ == '__main__':
    main()
