#!/usr/bin/env python3
"""
«Афк» в бою (21.10.2026): боец видит врага, патроны есть, стоит и не стреляет.

  python3 match/afk.py match/runs/l02_duel*.jsonl              куски матчей
  python3 match/afk.py match/runs_night_*/varka_trace.jsonl.gz  весь trace (gz можно)

Эпизод: подряд npc_pos, где видит цель (bsee), действие боя «убить врага» / «в укрытие» / «держать
позицию», магазин не пуст и не меняется, позиция не меняется — дольше MIN секунд.
Разбор по тому, что движок сам думал в начале эпизода (поля из varka_lkp, с 21.10):
  голова    — куда смотрела голова относительно врага: движок стреляет, только если она в 22.5°
  тело      — то же для тела: торс доворачивается сам только до 45° влево / 30° вправо (m_stalker.ltx)
  cke / ckm — луч из ствола: «попаду во врага» / «свой на линии» (object handler не стреляет при ckm)
"""
import collections
import gzip
import json
import math
import sys

MIN = 5.0
FIGHT = (19, 21, 23)  # убить врага, в укрытие, держать позицию


def load(path):
    pos = collections.defaultdict(list)
    op = gzip.open if path.endswith('.gz') else open
    with op(path, 'rt', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            if '"npc_pos"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            pos[e['npc']].append(e)
    return pos


def near(P, t):
    lo, hi = 0, len(P) - 1
    while lo < hi:
        m = (lo + hi) // 2
        if P[m]['t'] < t:
            lo = m + 1
        else:
            hi = m
    return P[lo] if P and abs(P[lo]['t'] - t) < 1500 else None


def angle(dx, dz, to):
    a = math.degrees(math.atan2(dx, dz) - math.atan2(*to))
    return (a + 180) % 360 - 180


def band(a):
    if a is None:
        return 'нет данных'
    a = abs(a)
    return '<22.5' if a < 22.5 else '22.5–45' if a < 45 else '45–90' if a < 90 else '>90'


def main():
    spells, fighters, seen = [], 0, 0.0
    for path in sys.argv[1:]:
        pos = load(path)
        for n, P in pos.items():
            fighters += 1
            start = None
            for a, b in zip(P, P[1:]):
                if a.get('bsee') == 1:
                    seen += (b['t'] - a['t']) / 1000
                ok = (a.get('bsee') == 1 and b.get('bsee') == 1 and a.get('aid') == 89 and a.get('aid2') in FIGHT
                      and a.get('mag', -1) > 0 and a.get('mag') == b.get('mag')
                      and math.hypot(a['px'] - b['px'], a['pz'] - b['pz']) < 0.3)
                if ok and start is None:
                    start = a
                elif not ok and start is not None:
                    dur = (a['t'] - start['t']) / 1000
                    if dur >= MIN:
                        o = near(pos.get(start.get('be', -1), []), start['t'])
                        body = head = None
                        if o:
                            to = (o['px'] - start['px'], o['pz'] - start['pz'])
                            if math.hypot(*to) > 1:
                                body = angle(start['dx'], start['dz'], to)
                                if start.get('hx') or start.get('hz'):
                                    head = angle(start['hx'], start['hz'], to)
                        spells.append(dict(dur=dur, file=path.split('/')[-1], npc=n, comm=start.get('comm'),
                                           wk=start.get('wk'), aid2=start.get('aid2'), body=body, head=head,
                                           cke=start.get('cke', -1), ckm=start.get('ckm', -1)))
                    start = None
    print(f'бойцов {fighters}; «афк» ≥{MIN:.0f} с: {len(spells)} эпизодов, {sum(s["dur"] for s in spells):.0f} с '
          f'из {seen:.0f} с «вижу врага»')
    if not spells:
        return
    for key, title in (('head', 'голова vs враг'), ('body', 'тело vs враг')):
        c = collections.Counter(band(s[key]) for s in spells)
        print(f'  {title}: ' + ', '.join(f'{k} {v}' for k, v in c.most_common()))
    c = collections.Counter((s['cke'], s['ckm']) for s in spells)
    names = {(-1, -1): 'не меряли', (1, 0): 'попаду, своих нет', (0, 0): 'НЕ попаду (линия закрыта)',
             (1, 1): 'свой на линии', (0, 1): 'свой на линии'}
    print('  луч ствола: ' + ', '.join(f'{names.get(k, k)} {v}' for k, v in c.most_common()))
    print('  по оружию: ' + ', '.join(f'{k} {v}' for k, v in collections.Counter(s['wk'] for s in spells).most_common()))
    print('самые длинные:')
    for s in sorted(spells, key=lambda s: -s['dur'])[:8]:
        h = f"{s['head']:+.0f}°" if s['head'] is not None else '?'
        b = f"{s['body']:+.0f}°" if s['body'] is not None else '?'
        print(f"  {s['dur']:5.1f} с  {s['file'][:34]:34s} {s['npc']:6d} {s['comm']:9s} {s['wk']:9s} "
              f"aid2={s['aid2']} голова {h} тело {b} cke={s['cke']} ckm={s['ckm']}")


if __name__ == '__main__':
    main()
