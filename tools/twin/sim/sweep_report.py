#!/usr/bin/env python3
"""sweep_report.py — отчёт по перебору sweep.lua (23.10.2026).

    python3 sweep_report.py sweeps/grenades.lua              отчёт в Markdown (stdout)
    python3 sweep_report.py sweeps/grenades.lua --progress   сколько боёв готово и когда кончится

Что считаем. Перевес доктрины X над Y в бою: d = (потери Y − потери X) / 4 (от −1 до +1); побед X/Y/ничьих.
Для каждого рычага мира — перевес на каждом его значении (с 95% интервалом) и размах. Если на одном значении
перевес уверенно > 0, а на другом уверенно < 0 — ПЕРЕВОРОТ: ответ «что лучше» зависит от этого рычага, и рычаг надо
калибровать по игре всерьёз. Если размах мал — рычаг на этот вопрос не влияет, его можно оставить как есть.
Двойник не откалиброван: это картина ЧУВСТВИТЕЛЬНОСТИ модели, а не правда об игре.
"""
import glob
import json
import math
import os
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))


def load(spec):
    name = os.popen(f"luajit -e \"print(dofile('{spec}').name)\"").read().strip()
    d = os.path.join(HERE, 'out', f'sweep_{name}')
    meta = json.load(open(os.path.join(d, 'meta.json')))
    rows = []
    for p in sorted(glob.glob(os.path.join(d, 'part_*.jsonl'))):
        for line in open(p):
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return d, meta, rows


def stat(xs):
    n = len(xs)
    if n == 0:
        return 0.0, 0.0, 0
    m = sum(xs) / n
    v = sum((x - m) ** 2 for x in xs) / max(1, n - 1)
    return m, 1.96 * math.sqrt(v / n), n


def fmt(m, ci):
    return f'{m:+.3f} ±{ci:.3f}'


def val(meta, k, i):
    v = meta['world'][k][i]
    return json.dumps(v, ensure_ascii=False)


def progress(spec):
    d, meta, rows = load(spec)
    done, total = len(rows), meta['total']
    msg = f'{done} / {total} боёв ({100 * done / total:.1f}%)'
    st = os.path.join(d, 'started.txt')
    if os.path.exists(st) and done:
        el = time.time() - os.path.getmtime(st)
        rate = done / el
        msg += f', {rate:.1f} боя/с, осталось ~{(total - done) / rate / 3600:.1f} ч'
    print(msg)


def main():
    spec = sys.argv[1]
    if '--progress' in sys.argv:
        return progress(spec)
    d, meta, rows = load(spec)
    knobs = list(meta['world'].keys())
    out = []
    w = out.append
    w(f"# Перебор «{meta['name']}» — отчёт\n")
    w(f"Боёв: **{len(rows)}** из {meta['total']}. Сценарии: {', '.join(meta['scen'])}. "
      f"Каждая пара играется со сменой сторон.\n")
    w("> Двойник не откалиброван по игре: это **чувствительность модели** — какие рычаги меняют ответ, а какие нет.\n")
    w("Перевес X: (потери Y − потери X)/4 на бой; > 0 — X лучше. ± — 95% интервал.\n")

    by_pair = defaultdict(list)
    for r in rows:
        by_pair[r['p']].append(r)

    # 1. общая картина
    w("## 1. Итог по парам\n")
    w("| X против Y | боёв | перевес X | побед X | побед Y | ничьих | " +
      " | ".join(f"{s}" for s in meta['scen']) + " |")
    w("|---|---|---|---|---|---|" + "---|" * len(meta['scen']))
    for p, pr in enumerate(meta['pairs']):
        rs = by_pair.get(p, [])
        if not rs:
            continue
        m, ci, n = stat([(r['ly'] - r['lx']) / 4 for r in rs])
        wx = sum(r['win'] == 1 for r in rs) / n
        wy = sum(r['win'] == -1 for r in rs) / n
        per = []
        for s in range(len(meta['scen'])):
            ms, cs, _ = stat([(r['ly'] - r['lx']) / 4 for r in rs if r['s'] == s])
            per.append(fmt(ms, cs))
        w(f"| **{pr[0]}** против {pr[1]} | {n} | {fmt(m, ci)} | {wx:.0%} | {wy:.0%} | {1 - wx - wy:.0%} | " +
          " | ".join(per) + " |")
    w("")

    # 2. чувствительность
    w("## 2. Чувствительность: какой рычаг меняет ответ\n")
    flips = []
    for p, pr in enumerate(meta['pairs']):
        rs = by_pair.get(p, [])
        if not rs:
            continue
        w(f"### {pr[0]} против {pr[1]}\n")
        w("| рычаг | значения → перевес X | размах | вывод |")
        w("|---|---|---|---|")
        lines = []
        for k in knobs:
            cells, ms = [], []
            for i in range(len(meta['world'][k])):
                m, ci, n = stat([(r['ly'] - r['lx']) / 4 for r in rs if r['k'][k] == i])
                cells.append((m, ci))
                ms.append(m)
                cells[-1] = (m, ci, f"{val(meta, k, i)}: {fmt(m, ci)}")
            span = max(ms) - min(ms)
            pos = any(m - ci > 0 for m, ci, _ in cells)
            neg = any(m + ci < 0 for m, ci, _ in cells)
            sig = any(abs(a[0] - b[0]) > a[1] + b[1] for a in cells for b in cells)
            verdict = '**ПЕРЕВОРОТ**' if pos and neg else ('влияет' if sig else '—')
            if pos and neg:
                flips.append((pr, k))
            lines.append((span, f"| {k} | {'; '.join(c[2] for c in cells)} | {span:.3f} | {verdict} |"))
        for _, l in sorted(lines, reverse=True):
            w(l)
        w("")

    # 3. экономика гранат: доктрина X пары vanilla/none — сколько стоит одна граната
    p0 = next((p for p, pr in enumerate(meta['pairs']) if pr[1] == 'none'), None)
    w(f"## 3. Экономика гранаты ({meta['pairs'][p0][0] if p0 is not None else '?'} кидает, противник без гранат)\n")
    if p0 is not None and by_pair.get(p0):
        rs = by_pair[p0]
        th = sum(r['gx'][0] for r in rs)
        kl = sum(r['gx'][1] for r in rs)
        ff = sum(r['gx'][2] for r in rs)
        dg = sum(r['gy'][3] for r in rs)
        w(f"Брошено {th}, убито врагов {kl} ({kl / max(1, th):.1%} на гранату), своих {ff} "
          f"({ff / max(1, th):.2%}), уклонений противника {dg}.\n")
        w("| рычаг | значения → убито врагов на гранату |")
        w("|---|---|")
        for k in knobs:
            cells = []
            for i in range(len(meta['world'][k])):
                sub = [r for r in rs if r['k'][k] == i]
                t = sum(r['gx'][0] for r in sub)
                c = sum(r['gx'][1] for r in sub)
                cells.append(f"{val(meta, k, i)}: {c / max(1, t):.1%}")
            w(f"| {k} | {'; '.join(cells)} |")
        w("")

    # 3б. срезы: идёт ли ещё бой (обе стороны живы) на каждом срезе — обрезает ли лимит бои
    if rows and 'snap' in rows[0]:
        w("## 3б. Срезы: доля боёв, которые ещё идут (у обеих сторон есть живые)\n")
        step = meta.get('snap', 30)
        for s_i, name in enumerate(meta['scen']):
            rs = [r for r in rows if r['s'] == s_i]
            if not rs:
                continue
            n_snap = max(len(r['snap']) for r in rs)
            cells = []
            for j in range(n_snap):
                on = 0
                for r in rs:
                    if j < len(r['snap']):
                        lx, ly = r['snap'][j]
                        on += lx < 4 and ly < 4
                cells.append(f"{(j + 1) * step} с: {on / len(rs):.0%}")
            fds = sorted(r['fd'] for r in rs if r['fd'] >= 0)
            fd = f", первая потеря — медиана {fds[len(fds) // 2]:.0f} с" if fds else ''
            w(f"- **{name}**: " + '; '.join(cells[::2]) + fd)
        w("")

    # 4. перевороты одной строкой
    w("## 4. Перевороты\n")
    if flips:
        for pr, k in flips:
            w(f"- **{pr[0]} против {pr[1]}** зависит от `{k}`: при одних значениях лучше X, при других — Y.")
    else:
        w("- Ни один рычаг не перевернул ни одного ответа (в пределах интервалов).")
    w("")

    # 5. хайлайты — бои для просмотра (двойник детерминирован: бой повторяется по номеру)
    w("## 5. Бои на утро (повтор: `luajit sim/sweep.lua <спек> --replay N` → trace для вьювера)\n")
    best = sorted(rows, key=lambda r: (r['gx'][1] + r['gy'][1]), reverse=True)[:5]
    ffs = [r for r in rows if r['gx'][2] + r['gy'][2] > 0][:5]
    for r in best:
        pr = meta['pairs'][r['p']]
        w(f"- №{r['n']}: {pr[0]} против {pr[1]}, {meta['scen'][r['s']]} — гранатами убито "
          f"{r['gx'][1]} + {r['gy'][1]}, потери {r['lx']}:{r['ly']}")
    for r in ffs:
        pr = meta['pairs'][r['p']]
        w(f"- №{r['n']}: огонь по своим гранатой ({r['gx'][2]} + {r['gy'][2]}), {pr[0]} против {pr[1]}")
    print('\n'.join(out))


if __name__ == '__main__':
    main()
