#!/usr/bin/env python3
"""
Трение «угроза → наведение → выстрел» (22.10.2026): где NPC видит врага и НЕ стреляет.

  python3 match/friction.py match/runs/night_squads_l03_agroprom_20261022_21*.jsonl     куски матчей

Считает по кускам матчей (нужен match_start):
  подход        сколько секунд от старта до первого «вижу врага» (bsee в npc_pos) и с какой скоростью идут
  время видения каждый тик npc_pos (0.5 с), где NPC видит свою цель, раскладывается по действию GOAP;
                «стреляет» = был выстрел (событие shot) в ±0.25 с от тика. Где доля видения большая,
                а стрельбы мало — там и трение.
  ответ         в него попали, пока он врага не видел: через сколько ответный выстрел
  ff_block      почему rx_ff запретил стрелять (с правки rx_ff 22.10): впритык / на линии
  перезарядка   с какого заполнения магазина (23.10: половина перезарядок — с полупустого и полнее)
"""
import bisect
import collections
import json
import math
import statistics
import sys

from shots import COMBAT

# верхние действия главного планировщика (doc/design/PLANNER_MAP.md)
TOP = {18803: 'rx_ff (свой на линии)', 193: 'state_mgr → бой', 188118: 'fight_from_cover', 1346: 'ранен лежит',
       188210: 'varka_clear', 188202: 'приказ мягкий', 188204: 'приказ жёсткий', 188112: 'добивание',
       188113: 'xr_danger', 89: 'бой', 91: 'опасность'}


def load(path):
    ev = []
    for line in open(path, encoding='utf-8', errors='replace'):
        try:
            ev.append(json.loads(line))
        except ValueError:
            pass
    ev.sort(key=lambda e: e['t'])
    return ev


def act(e):
    a2 = e.get('aid2', -1)
    if a2 != -1:
        return COMBAT.get(a2, f'бой {a2}')
    return TOP.get(e.get('aid', -1), f'top {e.get("aid", -1)}')


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))] if xs else float('nan')


def main():
    approach, speeds = [], []
    see, fire = collections.Counter(), collections.Counter()
    answer, silent = [], 0
    ff = collections.Counter()
    refill = []  # доля магазина перед перезарядкой
    n_match = 0
    for path in sys.argv[1:]:
        ev = load(path)
        start = [e for e in ev if e['ev'] == 'match_start']
        if not start:
            continue
        n_match += 1
        t0 = start[0]['t']
        pos, shots, death = collections.defaultdict(list), collections.defaultdict(list), {}
        for e in ev:
            if e['ev'] == 'npc_pos' and e['t'] >= t0:
                pos[e['npc']].append(e)
            elif e['ev'] == 'shot':
                shots[e['npc']].append(e['t'])
            elif e['ev'] == 'death':
                death[e['npc']] = e['t']
            elif e['ev'] == 'ff_block' and e['t'] >= t0:
                ff[e.get('why', '?')] += 1

        # подход: до первого «вижу» кем угодно
        first = [p['t'] for ps in pos.values() for p in ps if p.get('bsee') == 1]
        tc = min(first) if first else None
        approach.append((tc - t0) / 1000 if tc else None)
        for ps in pos.values():
            for a, b in zip(ps, ps[1:]):
                if tc and b['t'] <= tc and 300 < b['t'] - a['t'] < 900:
                    speeds.append(math.hypot(b['px'] - a['px'], b['pz'] - a['pz']) / ((b['t'] - a['t']) / 1000))

        # перезарядка: магазин того же ствола вырос между тиками
        for ps in pos.values():
            for a, b in zip(ps, ps[1:]):
                if a.get('wpn') == b.get('wpn') and a.get('mag', -1) >= 0 and b['mag'] > a['mag']:
                    refill.append(a['mag'] / b['mag'])

        # время видения по действиям
        for ps in pos.values():
            for p in ps:
                if p.get('bsee') != 1:
                    continue
                s = shots[p['npc']]
                i = bisect.bisect_left(s, p['t'] - 250)
                k = act(p)
                see[k] += 1
                fire[k] += i < len(s) and s[i] <= p['t'] + 250

        # ответ на попадание вслепую: первое попадание серии (пауза > 3 с), не смертельное
        last = {}
        for e in ev:
            if e['ev'] != 'hit' or e['t'] < t0 or e.get('bone') == 'from_death_callback':
                continue
            v, t = e['npc'], e['t']
            fresh = v not in last or t - last[v] > 3000
            last[v] = t
            if not fresh or (v in death and death[v] - t < 1500):
                continue
            before = [p for p in pos[v] if t - 600 <= p['t'] <= t]
            if before and before[-1].get('bsee') == 1:
                continue
            s = shots[v]
            i = bisect.bisect_left(s, t)
            if i < len(s) and s[i] - t < 10000:
                answer.append((s[i] - t) / 1000)
            else:
                silent += 1

    if not n_match:
        raise SystemExit('нет match_start — это не куски матчей из match/runs?')
    got = [a for a in approach if a is not None]
    print(f'матчей: {n_match}, без контакта вовсе: {len(approach) - len(got)}')
    if got:
        print(f'подход до первого «вижу»: медиана {statistics.median(got):.1f} с '
              f'(от {min(got):.1f} до {max(got):.1f})')
    if speeds:
        print(f'скорость на подходе: медиана {statistics.median(speeds):.2f} м/с, 75% до {q(speeds, .75):.2f} '
              f'(шаг в опасности 2.5, бег 4.5 по m_stalker.ltx)')

    tot, shot = sum(see.values()), sum(fire.values())
    if tot:
        print(f'\nвремя «вижу врага»: {tot / 2:.0f} с, со стрельбой {100 * shot / tot:.0f}%')
        print(f'  {"действие":26s} {"доля видения":>13s} {"стреляет":>9s}')
        for k, n in see.most_common(14):
            print(f'  {k:26s} {100 * n / tot:12.0f}% {100 * fire[k] / n:8.0f}%')

    if answer or silent:
        print(f'\nпопали, пока не видел врага: ответный огонь через медиану {statistics.median(answer):.1f} с, '
              f'75% до {q(answer, .75):.1f} с (n={len(answer)}); не ответил за 10 с: {silent}')
    if refill:
        print(f'\nперезарядок {len(refill)}: магазин был полон на медиану {100 * statistics.median(refill):.0f}%, '
              f'больше половины — {100 * sum(x > 0.5 for x in refill) / len(refill):.0f}%, больше 80% — {sum(x > 0.8 for x in refill)}')
    if ff:
        print('\nrx_ff, новые запреты:', ', '.join(f'{k} {v}' for k, v in ff.most_common()))


if __name__ == '__main__':
    main()
