#!/usr/bin/env python3
"""
Сверка запечки зрения с игрой (20.10.2026).

В игре varka_probe пускает вокруг игрока сферу лучей движковым ray_pick и пишет в trace
событие probe: начало, наклоны, по каждому лучу «дистанция:треугольник». Здесь те же лучи
пересчитываются по level.cform (vision/rays) и сравниваются.

  совпал       — тот же треугольник (или оба мимо)
  рядом        — треугольник другой, но дистанция ±2 см (луч в ребро/стык — не ошибка)
  расхождение  — всё остальное: в игре есть то, чего нет в файле (или наоборот)

Использование:
  python3 vision/check_probe.py <trace.jsonl> <папка уровня с level.cform> [--level l07_military]
"""
import argparse
import json
import math
import os
import subprocess
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
RAYS = os.path.join(HERE, 'rays')
NEAR = 0.02  # м


def probes(trace, level=None):
    for line in open(trace, encoding='utf-8', errors='replace'):
        if '"probe"' not in line:
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get('ev') == 'probe' and (not level or e.get('level') == level):
            yield e


def rays_of(e):
    """Лучи пробы так же, как их строит varka_probe (Lua: double → float в vector:set)."""
    naz = int(e['naz'])
    elev = [float(x) for x in str(e['elev']).split(',')]
    o = (e['ox'], e['oy'], e['oz'])
    out = []
    for el_deg in elev:
        el = el_deg * (math.pi / 180.0)
        ce, se = math.cos(el), math.sin(el)
        for i in range(naz):
            a = 2 * math.pi * i / naz
            out.append((*o, math.cos(a) * ce, se, math.sin(a) * ce, 150.0))
    return out, elev, naz


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('trace')
    ap.add_argument('level_dir')
    ap.add_argument('--level')
    args = ap.parse_args()

    ps = list(probes(args.trace, args.level))
    if not ps:
        raise SystemExit('в trace нет событий probe' + (f' для уровня {args.level}' if args.level else ''))

    all_rays, game = [], []
    for e in ps:
        r, _, _ = rays_of(e)
        all_rays += r
        for h in e['hits'].split(','):
            d, t = h.split(':')
            game.append((float(d), int(t)))
    R = np.array(all_rays, np.float32)
    G = np.array(game, dtype=[('d', 'f4'), ('t', 'i4')])
    if len(R) != len(G):
        raise SystemExit(f'лучей {len(R)}, ответов игры {len(G)} — формат пробы не сходится')

    with tempfile.TemporaryDirectory() as tmp:
        fin, fout = os.path.join(tmp, 'r.f32'), os.path.join(tmp, 'o.bin')
        R.tofile(fin)
        subprocess.run([RAYS, 'probe', os.path.join(args.level_dir, 'level.cform'), fin, fout], check=True)
        B = np.fromfile(fout, dtype=[('d', 'f4'), ('t', 'i4')])

    same = (G['t'] == B['t'])
    both_hit = (G['t'] >= 0) & (B['t'] >= 0)
    near = ~same & both_hit & (np.abs(G['d'] - B['d']) <= NEAR)
    bad = ~same & ~near
    game_only = bad & (G['t'] >= 0) & (B['t'] < 0)
    bake_only = bad & (G['t'] < 0) & (B['t'] >= 0)
    closer_in_game = bad & both_hit & (G['d'] < B['d'] - NEAR)

    n = len(G)
    print(f'проб {len(ps)}, лучей {n}')
    print(f'  совпал до треугольника: {same.mean():.2%}')
    print(f'  рядом (стык, ±{NEAR*100:.0f} см):  {near.mean():.2%}')
    print(f'  расхождение:            {bad.mean():.2%}')
    if bad.any():
        print(f'    в игре упор, в файле пусто:      {game_only.sum()}')
        print(f'    в файле упор, в игре пусто:      {bake_only.sum()}')
        print(f'    в игре упор БЛИЖЕ, чем в файле:  {closer_in_game.sum()}')
        print(f'    прочее:                          {(bad & ~game_only & ~bake_only & ~closer_in_game).sum()}')
        k = 0
        per = len(G) // len(ps)
        for idx in np.where(bad)[0][:10]:
            p = ps[idx // per]
            print(f'    проба #{idx // per} (vid {p.get("vid")}) луч {idx % per}: игра {G["d"][idx]:.2f} м tri {G["t"][idx]}'
                  f' — файл {B["d"][idx]:.2f} м tri {B["t"][idx]}')
            k += 1
    # по пробам: где расхождений больше всего — туда и смотреть глазами
    per = len(G) // len(ps)
    worst = sorted(((bad[i * per:(i + 1) * per].mean(), i) for i in range(len(ps))), reverse=True)[:5]
    if worst and worst[0][0] > 0:
        print('  худшие пробы:')
        for frac, i in worst:
            if frac == 0:
                break
            p = ps[i]
            print(f'    #{i}: {frac:.0%} лучей мимо, x={p["ox"]:.1f} z={p["oz"]:.1f} vid {p.get("vid")}')


if __name__ == '__main__':
    main()
