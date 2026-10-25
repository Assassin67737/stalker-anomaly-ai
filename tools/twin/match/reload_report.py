#!/usr/bin/env python3
"""Перезарядка за укрытием по кускам trace матчей (25.10.2026).

    python3 reload_report.py 'runs/vanilla_vs_varka_*_2026102[5-9]_*.jsonl' [--series '#042936']

1. Исходы пробежек reload_run → survive_end (reloaded / empty / rested / ...), где ранили и убивали.
2. Опасность перезарядки: попали / убит от последнего выстрела до 2 с после первого выстрела с новым магазином —
   ваниль на месте, VARKA на месте, VARKA за укрытием, VARKA дозарядка вне контакта (top_up).
3. Поломка ствола: бойцы, у которых магазин пуст ≥ 15 с подряд (ночь 042936: ваниль 1 из 600, VARKA 36 из 600 —
   спринт «ствол за спиной», починено в varka_survive v0.3).
"""
import argparse, collections as C, glob, json


def load(pattern, series):
    for fn in sorted(glob.glob(pattern)):
        head = open(fn).read()
        if series and series not in head:
            continue
        ev = [json.loads(l) for l in open(fn)]
        van = {e['sq'] for e in ev if e['ev'] == 'spawned' and e.get('vanilla')}
        per = C.defaultdict(list)
        for e in ev:
            per[e.get('npc')].append(e)
        yield per, van


def runs(per, R):
    for L in per.values():
        for i, e in enumerate(L):
            if e['ev'] != 'reload_run':
                continue
            th = None
            R['пробежек'] += 1
            for f in L[i + 1:]:
                if f['t'] - e['t'] > 40000:
                    R['конец: нет'] += 1
                    break
                k = f['ev']
                if k == 'survive_hold' and th is None:
                    th = f['t']
                    R['добежал'] += 1
                elif k == 'hit':
                    R['ранен ' + ('в укрытии' if th else 'на бегу')] += 1
                elif k == 'death':
                    R['конец: убит ' + ('в укрытии' if th else 'на бегу')] += 1
                    break
                elif k == 'survive_end':
                    R['конец: ' + f.get('why', '?')] += 1
                    break


def danger(per, van, D):
    for n, L in per.items():
        shots = [(e['t'], e['ammo'], e['sq']) for e in L if e['ev'] == 'shot']
        if not shots:
            continue
        stack = 'ваниль' if shots[0][2] in van else 'VARKA'
        hits = [e['t'] for e in L if e['ev'] == 'hit']
        dead = next((e['t'] for e in L if e['ev'] == 'death'), None)
        rr = [e['t'] for e in L if e['ev'] == 'reload_run']
        tu = [e['t'] for e in L if e['ev'] == 'wpn_topup']
        for (t0, a0, _), (t1, a1, _) in zip(shots, shots[1:]):
            if a1 <= a0 or t1 - t0 > 60000:
                continue
            kind = 'на месте'
            if any(t0 - 1000 <= t <= t1 for t in rr):
                kind = 'за укрытием'
            elif any(t0 - 1000 <= t <= t1 for t in tu):
                kind = 'дозарядка'
            w1 = t1 + 2000
            D[(stack, kind)].append(((t1 - t0) / 1000, any(t0 < t <= w1 for t in hits),
                                     dead is not None and t0 < dead <= w1))
        # убит посреди перезарядки — выстрела с новым магазином уже нет, эпизод без этого бы пропал
        tl, al, _ = shots[-1]
        if dead is not None and dead - tl < 15000:
            ran = any(tl - 1000 <= t <= dead for t in rr)
            if ran or al <= 3:
                kind = 'за укрытием' if ran else ('дозарядка' if any(tl - 1000 <= t <= dead for t in tu) else 'на месте')
                D[(stack, kind)].append(((dead - tl) / 1000, True, True))


def stuck(per, van, S):
    for L in per.values():
        P = [e for e in L if e['ev'] == 'npc_pos' and e.get('wpn')]
        if not P:
            continue
        stack = 'ваниль' if P[0]['sq'] in van else 'VARKA'
        S[(stack, 'бойцов')] += 1
        i = 0
        while i < len(P):
            if P[i].get('mag') != 0:
                i += 1
                continue
            j = i
            while j + 1 < len(P) and P[j + 1].get('mag') == 0 and P[j + 1].get('wpn') == P[i].get('wpn'):
                j += 1
            if P[j]['t'] - P[i]['t'] >= 15000:
                t0 = P[i]['t']
                ours = any(e['ev'] == 'reload_run' and t0 - 4000 <= e['t'] <= t0 + 1000 for e in L)
                S[(stack, 'пустой ствол ≥15 с')] += 1
                S[(stack, '  из них сразу после reload_run')] += ours
                break
            i = j + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pattern')
    ap.add_argument('--series', default='')
    a = ap.parse_args()
    R, D, S, n = C.Counter(), C.defaultdict(list), C.Counter(), 0
    for per, van in load(a.pattern, a.series):
        n += 1
        runs(per, R)
        danger(per, van, D)
        stuck(per, van, S)
    print(f'матчей: {n}\n\n1. пробежки на перезарядку')
    for k, v in R.most_common():
        print(f'   {k:26}{v}')
    print('\n2. опасность перезарядки (окно: последний выстрел → +2 с после первого с новым магазином)')
    print(f"   {'стек':7}{'как':13}{'эпизодов':>9}{'простой, с':>12}{'попали':>8}{'убит':>7}")
    for (s, k), L in sorted(D.items()):
        m = len(L)
        print(f'   {s:7}{k:13}{m:9}{sorted(x[0] for x in L)[m // 2]:12.1f}'
              f'{100 * sum(x[1] for x in L) / m:7.0f}%{100 * sum(x[2] for x in L) / m:6.0f}%')
    print('\n3. поломка ствола')
    for k, v in sorted(S.items()):
        print(f'   {k[0]:7}{k[1]:32}{v}')


if __name__ == '__main__':
    main()
