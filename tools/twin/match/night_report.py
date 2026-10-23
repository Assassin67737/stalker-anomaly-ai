#!/usr/bin/env python3
"""
Разбор серии матчей (21.10.2026): что из ночного прогона полезно.

  python3 night_report.py [спек] [--from N]      по умолчанию l07_night; --from 2 — пропустить пробный матч

Четыре сита, от грубого к тонкому:
  1. гигиена   — грязные (посторонние), по таймауту, без контакта: их не считаем или смотрим отдельно;
  2. дирижёры  — сила пресета с поправкой на расклад. Голый процент побед врёт: дирижёру может
                 просто чаще выпадать ветеран против новичков. Поэтому регрессия:
                     счёт_A = Σ эффект(пресет A) − Σ эффект(пресет B) + γ·Δранг + δ·Δчисло + фракции
                 (пресет «off» = ноль отсчёта; фракции — со штрафом-гребнем, их много, матчей мало),
                 доверительный интервал — бутстреп (пересэмплируем матчи 1000 раз);
  3. механики  — у каждой новой фичи есть инвариант, проверяем его по trace:
                 ствол ↔ дистанция, пистолет «последний шанс» (вход/выход), перезарядка сидя,
                 мораль по фракциям;
  4. хайлайты  — выбросы (разгром слабым, таймауты, бой без попаданий): их смотреть глазами во вьювере.
"""
import argparse
import glob
import json
import math
import os
import random
from collections import Counter, defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TIER = {'novice': 0, 'advanced': 1, 'veteran': 2}
# дальности как в varka_weapons.RANGE: {мин, лучше от, лучше до, макс}; в trace wk — класс ствола
RANGE = {'w_pistol': (0, 0, 20, 45), 'w_smg': (0, 0, 30, 60), 'w_shotgun': (0, 0, 15, 35),
         'w_rifle': (0, 0, 120, 250), 'w_sniper': (15, 40, 400, 800), 'launcher': (20, 35, 150, 300)}


def load_results(spec, first):
    rs = [json.loads(l) for l in open(os.path.join(HERE, 'results.jsonl'), encoding='utf-8')]
    return [r for r in rs if r.get('spec') == spec][first - 1:]


def events(path):
    for line in open(os.path.join(HERE, path), encoding='utf-8', errors='replace'):
        try:
            yield json.loads(line)
        except ValueError:
            pass


RANK = ['novice', 'trainee', 'experienced', 'professional', 'veteran', 'expert', 'master', 'legend']


def side_force(st):
    q = st['squads']
    lv = lambda s: RANK.index(s['rank']) * 2 / 7 if s.get('rank') else TIER.get(s['tier'], 1)  # бои по рангам: 0..7 → 0..2
    return sum(lv(s) * s['n'] for s in q) / max(1, sum(s['n'] for s in q)), \
        sum(s['n'] for s in q)


# ─── 1. гигиена ───────────────────────────────────────────────────────────────────────────────
def hygiene(rs):
    print(f"\n== 1. гигиена: {len(rs)} матчей")
    print('  исходы: ' + ', '.join(f'{k} {v}' for k, v in Counter(r['reason'] for r in rs).items()))
    dirty = [r['id'] for r in rs if not r.get('clean', True)]
    print(f"  грязных (посторонние): {len(dirty)} {dirty[:5]}")
    blind = [r['id'] for r in rs if r['hits']['A'] + r['hits']['B'] == 0]
    print(f"  без единого попадания: {len(blind)} {blind}")
    durs = sorted(r['dur'] for r in rs)
    print(f"  длительность: медиана {durs[len(durs) // 2]:.0f} с, от {durs[0]:.0f} до {durs[-1]:.0f}")
    return [r for r in rs if r.get('clean', True)]


# ─── 2. дирижёры ──────────────────────────────────────────────────────────────────────────────
def directors(rs, boot=1000):
    presets = sorted({r['directors'][s] for r in rs for s in 'AB'} - {'off'})
    facs = sorted({q['faction'] for r in rs for s in 'AB' for q in r['setup'][s]['squads']})
    cols = presets + ['Δранг', 'Δчисло'] + facs
    X, y, win = [], [], []
    for r in rs:
        row = [0.0] * len(cols)
        for s, sign in (('A', 1), ('B', -1)):
            d = r['directors'][s]
            if d != 'off':
                row[cols.index(d)] += sign
            for q in r['setup'][s]['squads']:
                row[cols.index(q['faction'])] += sign
        (ta, na), (tb, nb) = side_force(r['setup']['A']), side_force(r['setup']['B'])
        row[cols.index('Δранг')] = ta - tb
        row[cols.index('Δчисло')] = na - nb
        X.append(row)
        y.append(r['score_a'])
        win.append(r)
    X, y = np.array(X), np.array(y)
    # гребень только на фракциях: их 12, данных по каждой мало — без штрафа коэффициенты скачут
    pen = np.array([0.0] * (len(presets) + 2) + [1.0] * len(facs))

    def fit(Xs, ys):
        return np.linalg.solve(Xs.T @ Xs + np.diag(pen * 3.0) + 1e-6 * np.eye(len(cols)), Xs.T @ ys)

    beta = fit(X, y)
    rnd = np.random.default_rng(1)
    bs = np.array([fit(X[i], y[i]) for i in (rnd.integers(0, len(y), len(y)) for _ in range(boot))])
    lo, hi = np.percentile(bs, 5, axis=0), np.percentile(bs, 95, axis=0)

    print(f"\n== 2. дирижёры: счёт A ≈ сумма эффектов (ноль отсчёта — пресет off), 90% интервал бутстрепа")
    games = Counter()
    wins = Counter()
    for r in rs:
        for s, o in (('A', 1), ('B', -1)):
            d = r['directors'][s]
            if r['directors']['A'] == r['directors']['B']:
                continue  # зеркало ничего не говорит о силе пресета
            games[d] += 1
            wins[d] += (r['score_a'] * o) > 0
    for c in presets + ['off']:
        i = cols.index(c) if c in cols else None
        eff = f"{beta[i]:+.2f}  [{lo[i]:+.2f} … {hi[i]:+.2f}]" if i is not None else ' 0 (отсчёт)'
        sure = '' if i is None else ('  ← надёжно' if lo[i] > 0 or hi[i] < 0 else '')
        print(f"  {c:7s} {eff:28s} побед в незеркальных {wins[c]}/{games[c]}{sure}")
    for c in ('Δранг', 'Δчисло'):
        i = cols.index(c)
        print(f"  {c:7s} {beta[i]:+.2f}  [{lo[i]:+.2f} … {hi[i]:+.2f}]   за ступень ранга / за бойца")
    print('  фракции (со штрафом, грубо): ' + ', '.join(
        f'{f} {beta[cols.index(f)]:+.2f}' for f in sorted(facs, key=lambda f: -beta[cols.index(f)])))
    mir = [r['score_a'] for r in rs if r['directors']['A'] == r['directors']['B']]
    if mir:
        print(f"  зеркала ({len(mir)}): средний счёт A {np.mean(mir):+.2f} — шум/перекос сторон, ждём ≈0")
    return beta, cols


# ─── 3. механики ──────────────────────────────────────────────────────────────────────────────
def mechanics(rs):
    print('\n== 3. механики (по кускам trace)')
    dist_bad = Counter()
    dist_all = Counter()
    dist_hist = defaultdict(list)
    reload_cr = Counter()       # (сидя?, действие) при пустом магазине
    side_in, side_out, side_dur, side_d = 0, Counter(), [], []
    stuck_side = []
    moral = defaultdict(lambda: [0, 0, 0.0])  # фракция → [замеров, broken, сумма морали]
    for r in rs:
        pos, comm_of = {}, {}
        sq_comm = {}
        open_side = {}
        for e in events(r['run']):
            ev = e['ev']
            if ev == 'npc_pos':
                pos[e['npc']] = (e['px'], e['pz'])
                comm_of[e['npc']] = e.get('comm')
                sq_comm[e['sq']] = e.get('comm')
                be, wk = e.get('be', -1), e.get('wk', '')
                if be not in (-1, None) and be in pos and wk and e.get('bsee'):
                    d = math.dist(pos[e['npc']], pos[be])
                    dist_all[wk] += 1
                    dist_hist[wk].append(d)
                    if wk in RANGE and d > RANGE[wk][3]:
                        dist_bad[wk] += 1
                if e.get('mag') == 0 and wk and e.get('hp', 1) > 0:
                    reload_cr[(bool(e.get('cr')), e.get('aid'))] += 1
            elif ev == 'wpn_sidearm':
                side_in += 1
                side_d.append(e['d'])
                open_side[e['npc']] = e['t']
            elif ev == 'wpn_sidearm_end':
                side_out[e.get('why')] += 1
                if e['npc'] in open_side:
                    side_dur.append((e['t'] - open_side.pop(e['npc'])) / 1000)
            elif ev == 'death' and e['npc'] in open_side:
                side_out['умер с пистолетом'] += 1
                open_side.pop(e['npc'])
            elif ev == 'dir_moral':
                m = moral[sq_comm.get(e['sq'], '?')]
                m[0] += 1
                m[1] += e.get('st') == 'broken'
                m[2] += e.get('moral', 0)
        stuck_side += [(r['id'], n) for n in open_side]

    print('  ствол ↔ дистанция до видимого врага (замеры npc_pos):')
    for wk in sorted(dist_all, key=lambda k: -dist_all[k]):
        h = sorted(dist_hist[wk])
        print(f"    {wk:8s} {dist_all[wk]:6d} замеров, медиана {h[len(h) // 2]:5.0f} м, 90% {h[int(len(h) * .9)]:5.0f} м,"
              f" дальше макс. дальности: {dist_bad[wk] / dist_all[wk]:.0%}")
    sd = sorted(side_d)
    print(f"  пистолет-последний-шанс: входов {side_in}, дистанция входа медиана "
          f"{sd[len(sd) // 2] if sd else 0:.0f} м (порог 25)")
    print('    выходы: ' + ', '.join(f'{k} {v}' for k, v in side_out.items()) +
          f"; не вышли до конца матча: {len(stuck_side)}")
    if side_dur:
        sdu = sorted(side_dur)
        print(f"    с пистолетом: медиана {sdu[len(sdu) // 2]:.1f} с, макс {sdu[-1]:.0f} с")
    tot = sum(reload_cr.values())
    cr = sum(v for (c, _), v in reload_cr.items() if c)
    print(f"  пустой магазин (перезарядка): {tot} замеров, сидя {cr / max(tot, 1):.0%}; по действию: " +
          ', '.join(f"{a}{'·сидя' if c else ''} {v}" for (c, a), v in reload_cr.most_common(8)))
    print('  мораль по фракциям: доля «сломлен», средняя мораль')
    for f, (n, b, s) in sorted(moral.items(), key=lambda kv: kv[1][1] / max(kv[1][0], 1)):
        print(f"    {str(f):9s} broken {b / n:5.1%}   moral {s / n:.2f}   ({n} замеров)")


# ─── 4. хайлайты ──────────────────────────────────────────────────────────────────────────────
def highlights(rs, beta, cols):
    print('\n== 4. хайлайты — смотреть глазами (python3 ../server.py <кусок>)')
    i_t, i_n = cols.index('Δранг'), cols.index('Δчисло')
    rows = []
    for r in rs:
        (ta, na), (tb, nb) = side_force(r['setup']['A']), side_force(r['setup']['B'])
        expect = beta[i_t] * (ta - tb) + beta[i_n] * (na - nb)
        rows.append((r['score_a'] - expect, r))

    def line(r, note):
        sa, sb = r['setup']['A']['squads'][0], r['setup']['B']['squads'][0]
        print(f"  {note:14s} #{r['id'].split('-')[-1]:>3s} A {r['directors']['A']:6s} {sa['faction']} {sa['tier']}×{sa['n']}"
              f"  vs  B {r['directors']['B']:6s} {sb['faction']} {sb['tier']}×{sb['n']}"
              f"  → {r['score_a']:+.2f} {r['reason']} {r['dur']:.0f}с  {r['run']}")
    rows.sort(key=lambda x: x[0])
    for d, r in rows[:3]:
        line(r, f'сенсация B {d:+.1f}')
    for d, r in rows[-3:]:
        line(r, f'сенсация A {d:+.1f}')
    for r in rs:
        if r['reason'] == 'timeout':
            line(r, 'таймаут')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('spec', nargs='?', default='l07_night')
    ap.add_argument('--from', dest='first', type=int, default=1)
    a = ap.parse_args()
    rs = hygiene(load_results(a.spec, a.first))
    beta, cols = directors(rs)
    mechanics(rs)
    highlights(rs, beta, cols)


if __name__ == '__main__':
    main()
