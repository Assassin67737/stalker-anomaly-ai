#!/usr/bin/env python3
"""
Таблица узнавания оружия для игры (20.10.2026): кто может узнать ствол врага и о чём кричат всем.

Редкость — не поле в ltx, а ранг, с которого ствол впервые появляется в комплектах NPC
(items/settings/npc_loadouts/npc_loadouts_*.ltx). Узнают по звуку, а варианты одного ствола
(_camo, _custom, _duty…) звучат одинаково — поэтому редкость считается по звуковой группе
(snd_shoot): ранг группы = самый ранний ранг любого её ствола.

Правило юзера: новички (ранг < 6500 — novice+trainee, комплект *_novice) узнают только стволы
группы «новичок»; все остальные узнают всё. Стволы, которых нет в комплектах и чья звуковая
группа неизвестна, считаются не новичковыми.

Класс для выкрика (кричат всему отряду, кто бы ни узнал): sniper (kind w_sniper),
mg — пулемёт (ef_weapon_type 10), launcher — гранатомёт (ef_weapon_type 12 / w_explosive).

Выход: /mnt/games/ANOMALY_DEV/appdata/varka_vision/weapon_intel.txt — строки
  <секция> <novice 1|0> <класс|-> <kind>
Использование: python3 weapons/bake_weapon_intel.py
"""
import collections
import glob
import os
import re

from ltx import CONFIGS, get, load_sections

OUT = '/mnt/games/ANOMALY_DEV/appdata/varka_vision/weapon_intel.txt'
TIER = {'novice': 0, 'experienced': 1, 'veteran': 2, 'master': 3}


def loadout_tiers():
    first = {}
    for f in glob.glob(f'{CONFIGS}/items/settings/npc_loadouts/npc_loadouts_*.ltx'):
        sec = None
        for line in open(f, encoding='latin-1'):
            line = line.split(';')[0].strip()
            m = re.match(r'^\[([a-z_0-9]+)\]', line)
            if m:
                sec = m.group(1)
                continue
            if not sec or not line or '=' in line:
                continue
            t = next((TIER[k] for k in TIER if f'_{k}_' in sec + '_'), None)
            w = line.split(':')[0].strip()
            if t is not None and w.startswith('wpn_'):
                first[w] = min(first.get(w, 9), t)
    return first


def main():
    S = load_sections('items/weapons/**/*.ltx')
    first = loadout_tiers()
    snd = lambda w: (get(S, w, 'snd_shoot') or '').split(',')[0].strip() or None
    group_tier = collections.defaultdict(lambda: 9)
    for w, t in first.items():
        g = snd(w)
        if g:
            group_tier[g] = min(group_tier[g], t)

    rows, counts = [], collections.Counter()
    for w in sorted(S):
        if not w.startswith('wpn_') or not get(S, w, 'class'):
            continue
        kind = get(S, w, 'kind') or '-'
        if kind in ('w_misc', 'w_melee'):
            continue
        g = snd(w)
        tier = group_tier[g] if g in group_tier else first.get(w, 1)
        ef = get(S, w, 'ef_weapon_type')
        cls = ('mg' if ef == '10' else 'launcher' if ef == '12' or kind == 'w_explosive'
               else 'sniper' if kind == 'w_sniper' else '-')  # ef 11 бывает и у автоматов (АШ-12)
        novice = 1 if tier == 0 else 0
        rows.append(f'{w} {novice} {cls} {kind}')
        counts[(novice, cls)] += 1

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, 'w').write('\n'.join(rows) + '\n')
    print(f'{len(rows)} стволов → {OUT}')
    print(f'  знают новички: {sum(v for (n, _), v in counts.items() if n)}, только опытные+: '
          f'{sum(v for (n, _), v in counts.items() if not n)}')
    print('  выкрик: ' + ', '.join(f'{c} {sum(v for (_, cc), v in counts.items() if cc == c)}'
                                   for c in ('sniper', 'mg', 'launcher')))


if __name__ == '__main__':
    main()
