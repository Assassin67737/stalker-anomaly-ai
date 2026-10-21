#!/usr/bin/env python3
"""
Куда летят пули NPC (21.10.2026): разбор события shot из varka_match.

  python3 match/shots.py match/runs/l02_duel_*.jsonl      файлы trace (кусок матча или весь trace)

На каждый выстрел игра пишет: видят ли глаза врага (see), сколько мс с последнего «вижу» (since),
свободна ли линия до груди врага от ствола (mc) и от глаз (ec), где луч упёрся (mhit, ehit), дистанцию (d),
сидит ли (cr) и действие боя (aid2). Отсюда корзины:

  чисто              ствол видит грудь врага
  ствол в укрытие    глаза видят, ствол упёрся — «голова над бетоном, ствол в бетоне»
  по памяти          глаза уже не видят (враг спрятался), стреляет туда, где видел
  оба закрыты        глаза «видят» (движок: сквозь листву/полупрозрачное), а лучи по статике — в стену

Где упёрлась пуля: у себя (< 2 м — своё укрытие), посередине, у врага (последние 3 м — его укрытие).
"""
import collections
import json
import sys

# действия боевого планировщика (stalker_decision_space.h, eWorldOperator…)
COMBAT = {15: 'ищет патроны', 16: 'целится', 17: 'готовится (перезарядка)', 18: 'готов к обходу',
          19: 'убить врага', 20: 'отход', 21: 'в укрытие', 22: 'выглянуть', 23: 'держать позицию',
          24: 'держать дистанцию', 25: 'обход', 26: 'поиск', 27: 'от гранаты', 28: 'внезапная атака',
          29: 'стрельба по невидимому', 34: 'после боя', 39: 'граната', 40: 'бегом в укрытие'}


def kind(sec):
    for k, names in (('пистолет', ('pm', 'fort', 'colt', 'beretta', 'usp', 'glock', 'pb', 'aps', 'deagle', 'mp412',
                                   'walther', 'cz75', 'hpsa', 'sig220', 'pistol', 'gsh18', 'mp443', 'fn57', 'vz61')),
                     ('дробовик', ('toz', 'bm16', 'spas', 'saiga', 'wincheaster', 'winchester', 'protecta', 'ks23',
                                   'mossberg', 'remington', 'striker', 'usas', 'shotgun', 'ithaca', 'nova', 'm1014')),
                     ('ПП', ('mp5', 'bizon', 'kiparis', 'ump', 'p90', 'mp7', 'pp2000', 'pp19', 'vityaz', 'kedr',
                             'uzi', 'mac10', 'mp9', 'vector')),
                     ('снайперка', ('svd', 'svu', 'vintorez', 'vssk', 'mosin', 'trg', 'awm', 'm24', 'sv98', 'l96',
                                    'gauss', 'k98', 'wa2000', 'm98', 'mk14', 'sr25', 'm40', 'barrett', 'remington700'))):
        if any(n in sec for n in names):
            return k
    return 'автомат'


def bucket(e):
    if 'mc' not in e:
        return 'нет врага'
    if e['mc']:
        return 'чисто'
    if not e.get('see'):
        return 'по памяти'
    if e['ec']:
        return 'ствол в укрытие'
    return 'оба закрыты'


def where(e):
    if e.get('mc', 1):
        return None
    h, d = e.get('mhit', 0), e.get('d', 0)
    if h < 2:
        return 'у себя (<2 м)'
    if h > d - 3:
        return 'у врага (≤3 м до него)'
    return 'посередине'


def pct(n, tot):
    return f'{n:5d}  {100 * n / tot:5.1f}%' if tot else f'{n:5d}'


def table(title, counter, tot, order=None):
    print(f'\n{title}')
    for k in (order or [k for k, _ in counter.most_common()]):
        if counter.get(k):
            print(f'  {k:28s} {pct(counter[k], tot)}')


def main():
    shots = []
    for path in sys.argv[1:]:
        for line in open(path, encoding='utf-8', errors='replace'):
            if '"shot"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get('ev') == 'shot':
                shots.append(e)
    if not shots:
        raise SystemExit('событий shot нет — игра не перезапущена после правки varka_match?')

    tot = len(shots)
    order = ['чисто', 'ствол в укрытие', 'по памяти', 'оба закрыты', 'нет врага']
    print(f'выстрелов: {tot}, стрелков: {len({e["npc"] for e in shots})}')
    table('куда идут пули', collections.Counter(bucket(e) for e in shots), tot, order)

    blocked = [e for e in shots if not e.get('mc', 1)]
    table('где упёрлись (из закрытых)', collections.Counter(where(e) for e in blocked), len(blocked),
          ['у себя (<2 м)', 'посередине', 'у врага (≤3 м до него)'])

    print('\nпо оружию: всего / в препятствие')
    by = collections.defaultdict(lambda: [0, 0])
    for e in shots:
        k = kind(e.get('wpn', ''))
        by[k][0] += 1
        by[k][1] += 0 if e.get('mc', 1) else 1
    for k, (n, b) in sorted(by.items(), key=lambda x: -x[1][0]):
        print(f'  {k:12s} {n:5d}  в препятствие {100 * b / n:5.1f}%')

    print('\nпо действию боя: всего / в препятствие / сидя')
    by = collections.defaultdict(lambda: [0, 0, 0])
    for e in shots:
        k = COMBAT.get(e.get('aid2', -1), f"aid {e.get('aid', -1)}/{e.get('aid2', -1)}")
        by[k][0] += 1
        by[k][1] += 0 if e.get('mc', 1) else 1
        by[k][2] += e.get('cr', 0)
    for k, (n, b, c) in sorted(by.items(), key=lambda x: -x[1][0]):
        print(f'  {k:28s} {n:5d}  в препятствие {100 * b / n:5.1f}%  сидя {100 * c / n:5.1f}%')

    # недоворот: движок жмёт на спуск, пока взгляд в ai_aim_fire_angle (22.5°) от врага
    for key, title in (('ab', 'тело по горизонтали'), ('aw', 'ствол (объект оружия), полный угол')):
        got = [e for e in shots if e.get(key, -1) >= 0 and e.get('see')]
        if not got:
            continue
        print(f'\nнедоворот при выстреле — {title}, видя врага ({len(got)}): всего / в препятствие')
        edges = [(0, 3), (3, 7), (7, 12), (12, 22.5), (22.5, 181)]
        for lo, hi in edges:
            b = [e for e in got if lo <= e[key] < hi]
            if b:
                blk = sum(0 if e.get('mc', 1) else 1 for e in b)
                print(f'  {lo:5.1f}–{hi if hi < 181 else "…":<5}°  {pct(len(b), len(got))}   в препятствие {100 * blk / len(b):5.1f}%')
        s = sorted(e[key] for e in got)
        print(f'  медиана {s[len(s) // 2]:.1f}°, 90% до {s[int(len(s) * 0.9)]:.1f}°')

    mem = [e for e in shots if 'mc' in e and not e.get('see')]
    if mem:
        s = sorted(e['since'] for e in mem if e.get('since', -1) >= 0)
        if s:
            print(f'\nпо памяти: с последнего «вижу» медиана {s[len(s) // 2] / 1000:.1f} с, '
                  f'90% до {s[int(len(s) * 0.9)] / 1000:.1f} с, макс {s[-1] / 1000:.1f} с')


if __name__ == '__main__':
    main()
