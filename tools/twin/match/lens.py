#!/usr/bin/env python3
"""
Объектив этюда (30.10.2026): чтобы не смотреть один и тот же бой в 50-й раз.

  python3 match/lens.py etude_vanilla_1v1                 все матчи спека из results.jsonl
  python3 match/lens.py etude_vanilla_1v1 160446 161446   только эти серии (время запуска в id: #161446-3)

Каждый матч — одна строка: кто первым увидел врага (bsee в npc_pos), выстрелил (shot), попал (hit), кто выжил.
Дальше — правила «первым X → победил k из n» и перекосы: точка спавна, группировка.
Суть этюда — развилка, после которой исход уже решён. Правило, которое держится почти всегда, — это
развилка найдена; смотреть глазами нужно только **исключения** из неё: внизу их список с файлами для повтора.
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(path):
    ev = []
    for line in open(path, encoding='utf-8', errors='replace'):
        try:
            ev.append(json.loads(line))
        except ValueError:
            pass
    ev.sort(key=lambda e: e['t'])
    return ev


def sides_of(start):
    return {s: {int(x) for x in str(start[s.lower()]).split(',') if x} for s in 'AB'}


def firsts(ev):
    """Секунды от старта до первого «вижу» / выстрела / попадания каждой стороны."""
    start = next((e for e in ev if e.get('ev') == 'match_start'), None)
    if not start:
        return None
    sq = sides_of(start)
    side = lambda q: next((s for s in 'AB' if q in sq[s]), None)
    out = {k: {} for k in ('see', 'shot', 'hit')}
    for e in ev:
        if e['t'] < start['t']:
            continue
        k, s = e.get('ev'), None
        if k == 'npc_pos' and e.get('bsee') == 1:
            k, s = 'see', side(e.get('sq'))
        elif k == 'shot':
            s = side(e.get('sq'))
        elif k == 'hit':
            s = side(e.get('wsq'))  # попал тот, чей отряд стрелял
        if k in out and s and s not in out[k]:
            out[k][s] = (e['t'] - start['t']) / 1000
    return out


def who_first(d):
    """'A' / 'B' / '=' (разница меньше тика npc_pos) / '-' (никто)."""
    if not d:
        return '-'
    if len(d) == 1:
        return next(iter(d))
    if abs(d['A'] - d['B']) < 0.5:
        return '='
    return min(d, key=d.get)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    spec, series = sys.argv[1], sys.argv[2:]
    rows = []
    for line in open(os.path.join(HERE, 'results.jsonl'), encoding='utf-8'):
        r = json.loads(line)
        sid = r.get('id', '')
        if not sid.startswith(spec + '#'):
            continue
        if series and sid.split('#')[1].split('-')[0] not in series:
            continue
        path = os.path.join(HERE, r.get('run') or '')
        f = firsts(load(path)) if r.get('run') and os.path.exists(path) else None
        if f is None:
            continue
        win = 'A' if r['loss']['B'] > r['loss']['A'] else 'B' if r['loss']['A'] > r['loss']['B'] else '='
        q = {s: r['setup'][s]['squads'][0] for s in 'AB'}
        at = {s: (round(q[s]['at']['x']), round(q[s]['at']['z'])) for s in 'AB'}
        comm = {s: (q[s].get('kit') or {}).get('community') or q[s]['faction'] for s in 'AB'}
        rows.append(dict(id=sid, f=f, win=win, at=at, comm=comm, dur=r['dur'], run=r['run']))
    if not rows:
        sys.exit('матчей нет (спек? серии? есть ли куски в runs/?)')

    print(f'{"матч":<28} {"увидел":>13} {"выстрелил":>13} {"попал":>13}  выжил  с')
    for w in rows:
        cell = lambda k: f"{who_first(w['f'][k])} " + '/'.join(
            f"{w['f'][k][s]:.0f}" if s in w['f'][k] else '·' for s in 'AB')
        print(f"{w['id']:<28} {cell('see'):>13} {cell('shot'):>13} {cell('hit'):>13}  {w['win']:^5}  {w['dur']:.0f}")
    print('  (первым A/B, = почти одновременно; дальше секунды A/B от старта, · — не было)')

    print('\nправила — кто первым X, тот и выжил:')
    for k, name in (('see', 'увидел'), ('shot', 'выстрелил'), ('hit', 'попал')):
        dec = [w for w in rows if who_first(w['f'][k]) in 'AB' and w['win'] in 'AB']
        ok = sum(who_first(w['f'][k]) == w['win'] for w in dec)
        print(f'  первым {name:<10} {ok:>3} из {len(dec):<3}' + (f'  ({100 * ok / len(dec):.0f}%)' if dec else ''))

    print('\nперекосы (кто выжил):')
    for name, key in (('точка спавна', lambda w, s: w['at'][s]), ('группировка', lambda w, s: w['comm'][s])):
        c = collections.Counter(key(w, w['win']) for w in rows if w['win'] in 'AB')
        n = collections.Counter(key(w, s) for w in rows for s in 'AB' if w['win'] in 'AB')
        print(f'  {name}: ' + ',  '.join(f'{k}: {c[k]} из {n[k]}' for k in n))
    print('  (одна точка у A во всех матчах = перекос точки и стороны не разделить — нужен "mirror": true)')

    print('\nисключения — попал первым, но не выжил (смотреть глазами только их):')
    odd = [w for w in rows if who_first(w['f']['hit']) in 'AB' and w['win'] in 'AB'
           and who_first(w['f']['hit']) != w['win']]
    for w in odd:
        print(f"  {w['id']:<28} {w['run']}")
    if not odd:
        print('  нет')


if __name__ == '__main__':
    main()
