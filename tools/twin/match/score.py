#!/usr/bin/env python3
"""
Оценка исхода матча (20.10.2026). Читает кусок trace одного матча (от match_start до match_end).

Счёт стороны A (у B — тот же с обратным знаком, игра с нулевой суммой):

  счёт = W_KILL  × (потери B − потери A)          потери = вес убитых / вес на старте; вес бойца = 1 + ранг/12000
       + W_CTRL  × (точка A − точка B)              доля времени, когда в радиусе точки только свои
       + W_BREAK × (сломлен B − сломлен A)          доля замеров морали в состоянии broken
       + W_WIN   × исход                            +1 выбили всех, −1 выбили нас, 0 время вышло
       − W_FF    × доля своих попаданий по своим

Почему так:
  - вес по рангу — размен «новичок за ветерана» не равен нулю (против камикадзе);
  - точка — без неё выгодно не воевать вовсе («мир», как в Квейке);
  - сломать мораль дешевле, чем убить, и это тоже результат;
  - исход — небольшой бонус, иначе ученик тянет время ради точки и не добивает.

Использование:
  python3 match/score.py <кусок trace.jsonl>          печать разбора
"""
import json
import sys

W_KILL, W_CTRL, W_BREAK, W_WIN, W_FF = 1.0, 0.5, 0.25, 0.5, 0.25
VETERAN = 12000


def rank_w(r):
    return 1 + (r or 0) / VETERAN


def load(path):
    out = []
    for line in open(path, encoding='utf-8', errors='replace'):
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def score(events):
    start = next((e for e in events if e['ev'] == 'match_start'), None)
    end = next((e for e in events if e['ev'] == 'match_end'), None)
    if not (start and end):
        raise ValueError('в куске нет match_start / match_end')
    # только то, что было В матче: после match_end раннер убирает выживших (это тоже смерти)
    t0, t1 = start['t'], end['t']
    inside = [e for e in events if t0 <= e.get('t', 0) <= t1]
    side_of = {}
    for side in ('a', 'b'):
        for sq in str(start[side]).split(','):
            if sq.strip():
                side_of[int(sq)] = side.upper()

    # состав на старте: первый npc_pos каждого бойца отрядов матча
    who_side, w0 = {}, {'A': 0.0, 'B': 0.0}
    rank = {}
    for e in events:
        if e['ev'] == 'npc_pos' and e['sq'] in side_of and e['npc'] not in who_side:
            s = side_of[e['sq']]
            who_side[e['npc']] = s
            rank[e['npc']] = e.get('rank', 0)
            w0[s] += rank_w(e.get('rank', 0))

    lost = {'A': 0.0, 'B': 0.0}
    deaths = {'A': 0, 'B': 0}
    for e in inside:
        if e['ev'] == 'death' and e['npc'] in who_side:
            s = who_side[e['npc']]
            lost[s] += rank_w(rank[e['npc']])  # вес как на старте — иначе потери могут превысить 100%
            deaths[s] += 1
    loss = {s: (lost[s] / w0[s] if w0[s] else 0) for s in lost}

    brk = {'A': [0, 0], 'B': [0, 0]}
    for e in inside:
        if e['ev'] == 'dir_moral' and e['sq'] in side_of:
            b = brk[side_of[e['sq']]]
            b[0] += e.get('st') == 'broken'
            b[1] += 1
    broken = {s: (v[0] / v[1] if v[1] else 0) for s, v in brk.items()}

    hits = {'A': [0, 0], 'B': [0, 0]}   # [по своим, всего] у стрелков стороны
    for e in inside:
        if e['ev'] == 'hit' and e.get('who') in who_side:
            s = who_side[e['who']]
            hits[s][1] += 1
            hits[s][0] += who_side.get(e['npc']) == s
    ff = {s: (v[0] / v[1] if v[1] else 0) for s, v in hits.items()}

    # посторонние (21.10): по бойцам матча попадает кто-то не из матча — выживший прошлого матча,
    # местный отряд. Такой матч не чистый: счёт в нём — не заслуга сторон.
    foreign = {'A': 0, 'B': 0}
    for e in inside:
        if e['ev'] == 'hit' and e['npc'] in who_side and e.get('who') not in who_side \
                and e.get('who') not in (None, e['npc']):
            foreign[who_side[e['npc']]] += 1
        # смерть не от бойца матча (выброс, аномалия, посторонний) — тоже грязь
        if e['ev'] == 'death' and e['npc'] in who_side and e.get('killer') not in who_side \
                and e.get('killer') not in (None, e['npc']):
            foreign[who_side[e['npc']]] += 1

    dur = max(end.get('dur', 0), 1e-6)
    ctrl = {'A': end.get('ctrl_a', 0) / dur, 'B': end.get('ctrl_b', 0) / dur}
    if end['reason'] == 'eliminated':
        outcome = 1 if end.get('alive_b', 0) == 0 and end.get('alive_a', 0) > 0 else \
                 -1 if end.get('alive_a', 0) == 0 and end.get('alive_b', 0) > 0 else 0
    else:
        outcome = 0

    terms = {
        'kill': W_KILL * (loss['B'] - loss['A']),
        'ctrl': W_CTRL * (ctrl['A'] - ctrl['B']),
        'break': W_BREAK * (broken['B'] - broken['A']),
        'win': W_WIN * outcome,
        'ff': -W_FF * ff['A'] + W_FF * ff['B'],
    }
    total = sum(terms.values())
    return {
        'id': start['id'], 'level': start.get('level'), 'reason': end['reason'], 'dur': round(dur, 1),
        'score_a': round(total, 3), 'terms': {k: round(v, 3) for k, v in terms.items()},
        'loss': {k: round(v, 3) for k, v in loss.items()}, 'deaths': deaths,
        'start_n': {s: sum(1 for x in who_side.values() if x == s) for s in 'AB'},
        'ctrl': {k: round(v, 3) for k, v in ctrl.items()}, 'broken': {k: round(v, 3) for k, v in broken.items()},
        'ff': {k: round(v, 3) for k, v in ff.items()}, 'hits': {s: hits[s][1] for s in 'AB'},
        'foreign_hits': foreign, 'clean': not any(foreign.values()),
    }


def show(r):
    win = {1: 'A выбила B', -1: 'B выбила A', 0: 'без разгрома'}
    print(f"матч {r['id']} ({r['level']}): {r['reason']}, {r['dur']} с — "
          f"{'A' if r['score_a'] > 0 else 'B' if r['score_a'] < 0 else 'ничья'} {abs(r['score_a']):.2f}")
    print(f"  бойцов A/B: {r['start_n']['A']}/{r['start_n']['B']}, убито {r['deaths']['A']}/{r['deaths']['B']}, "
          f"потери по весу {r['loss']['A']:.0%}/{r['loss']['B']:.0%}")
    print(f"  точка {r['ctrl']['A']:.0%}/{r['ctrl']['B']:.0%}, сломлены {r['broken']['A']:.0%}/{r['broken']['B']:.0%}, "
          f"попаданий {r['hits']['A']}/{r['hits']['B']}, по своим {r['ff']['A']:.0%}/{r['ff']['B']:.0%}")
    print('  слагаемые счёта A: ' + ', '.join(f'{k} {v:+.2f}' for k, v in r['terms'].items()))
    if not r.get('clean', True):
        fh = r['foreign_hits']
        print(f"  ГРЯЗНЫЙ: посторонние (попадания и убийства) по A {fh['A']}, по B {fh['B']} — счёт не чистый")


if __name__ == '__main__':
    show(score(load(sys.argv[1])))
