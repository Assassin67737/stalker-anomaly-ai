#!/usr/bin/env python3
"""
Сверка сосуда (24.10.2026): одни и те же замеры ТЕЛА по trace игры и trace двойника — рядом, в одной таблице.

    python3 tools/twin/sim/vessel.py --game 'match/runs/night_ranks*.jsonl' --twin 'sim/out/vessel_*.jsonl'

Мерим только то, что не зависит от того, чей мозг ведёт бой (ваниль, VARKA, доктрина двойника):
  попадание на выстрел по дистанции и позе стрелка, урон пули, пуль до смерти, кости, скорость ходьбы/бега,
  скорость доворота, дистанция обнаружения, ритм очередей, раненые, время до первого выстрела / попадания / смерти.
Попадание засчитываем выстрелу, только если стрелок стрелял за 0.5 с до него (гранаты и игрок не мешают).
События hit одной пули (игра пишет 2–3 в одну мс по костям) склеиваются, служебные (from_death_callback, урон 1e5
от уборки) выкидываются — merge_hits.
Пути — glob относительно tools/twin (или абсолютные). Проценты — доля, в скобках — сколько случаев.
"""
import argparse
import bisect
import collections
import glob
import json
import math
import os

TWIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

DBINS = [(0, 10), (10, 20), (20, 35), (35, 60), (60, 1e9)]
HP_SCALE = 111          # hp в npc_pos — доля; в единицах урона корпуса (игра: урон / Δhp по костям ×1)

PISTOL = ('wpn_pb', 'wpn_pm', 'wpn_fort', 'wpn_hpsa', 'wpn_beretta', 'wpn_colt', 'wpn_usp', 'wpn_desert', 'wpn_walther',
          'wpn_sig220', 'wpn_glock', 'wpn_mp412', 'wpn_gsh18', 'wpn_aps', 'wpn_cz75', 'wpn_pl15', 'wpn_sw', 'wpn_tt33',
          'wpn_rhino', 'wpn_mp443', 'wpn_fn57', 'wpn_p226', 'wpn_eagle', 'wpn_nagant')
SHOTGUN = ('wpn_toz', 'wpn_bm16', 'wpn_wincheaster', 'wpn_spas', 'wpn_saiga', 'wpn_protecta', 'wpn_mossberg',
           'wpn_ks23', 'wpn_remington', 'wpn_ithaca', 'wpn_usas', 'wpn_vepr', 'wpn_m1014', 'wpn_benelli', 'wpn_moss')
SMG = ('wpn_mp5', 'wpn_bizon', 'wpn_pp2000', 'wpn_kiparis', 'wpn_ppsh', 'wpn_vityaz', 'wpn_mp7', 'wpn_uzi', 'wpn_ump',
       'wpn_vz61', 'wpn_kedr', 'wpn_p90', 'wpn_mp9', 'wpn_kriss', 'wpn_sr2', 'wpn_aks74u', 'wpn_ak74u')
SNIPER = ('wpn_svd', 'wpn_svu', 'wpn_gauss', 'wpn_mosin', 'wpn_sv98', 'wpn_wa2000', 'wpn_vssk', 'wpn_l96', 'wpn_m98',
          'wpn_k98', 'wpn_trg', 'wpn_m24', 'wpn_remington700', 'wpn_sks', 'wpn_vintorez', 'wpn_val', 'wpn_m82')


def wclass(w):
    if not w or w.startswith('w_'):
        return w or '?'
    for pre, k in ((PISTOL, 'w_pistol'), (SHOTGUN, 'w_shotgun'), (SNIPER, 'w_sniper'), (SMG, 'w_smg')):
        if w.startswith(pre):
            return k
    return 'w_rifle'


def files(pat):
    p = pat if os.path.isabs(pat) else os.path.join(TWIN, pat)
    return sorted(glob.glob(p))


def q(xs, p):
    if not xs:
        return float('nan')
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(p * len(xs)))]


def load(paths):
    """Разбить trace на матчи (match_start … match_end); вне матча — пропускаем."""
    matches = []
    for fn in paths:
        cur = None
        for line in open(fn, errors='replace'):
            if '"ev"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            ev = e['ev']
            if ev == 'match_start':
                cur = {'t0': e['t'], 'ev': [], 'level': e.get('level', '')}
                matches.append(cur)
            elif cur is not None:
                cur['ev'].append(e)
                if ev == 'match_end':
                    cur['t1'] = e['t']
                    cur = None
    return matches


def merge_hits(evs):
    """Игра: одна пуля даёт 2–3 события hit в одну мс по разным костям (урон делится) — склеиваем в одно
    попадание (жертва, стрелок, мс) с суммарным уроном и костью самой большой части."""
    out, last = [], {}
    for e in evs:
        if e['ev'] == 'hit':
            # служебные: на смерть игра пишет hit с костью from_death_callback и уроном 1; kill/vanish уборки — 1e5
            if e.get('bone') == 'from_death_callback' or e.get('amount', 0) > 1000:
                continue
            k = (e['npc'], e.get('who'), e['t'])
            if k in last:
                h = last[k]
                if e.get('amount', 0) > h['_max']:
                    h['_max'], h['bone'] = e.get('amount', 0), e.get('bone')
                h['amount'] = h.get('amount', 0) + e.get('amount', 0)
                continue
            e = dict(e, _max=e.get('amount', 0))
            last[k] = e
        out.append(e)
    return out


def measure(matches):
    R = collections.defaultdict(list)
    C = collections.Counter()
    for m in matches:
        evs = merge_hits(m['ev'])
        shots = collections.defaultdict(list)       # npc → [t]
        pos = collections.defaultdict(list)         # npc → [(t, x, z, dx, dz, cr, bsee, be, wnd)]
        hits_on = collections.Counter()
        first = {}
        for e in evs:
            ev = e['ev']
            if ev == 'shot':
                shots[e['npc']].append(e['t'])
                first.setdefault('shot', e['t'])
            elif ev == 'npc_pos':
                pos[e['npc']].append((e['t'], e['px'], e['pz'], e.get('dx', 0), e.get('dz', 0), e.get('cr', 0),
                                      e.get('bsee', 0), e.get('be', -1), e.get('wnd', 0), e.get('hp', 1)))
        # ── выстрелы: дистанция, поза, класс
        for e in evs:
            if e['ev'] == 'shot' and e.get('d') is not None and e.get('enemy', -1) != -1:
                C['shot'] += 1
                b = next(i for i, (lo, hi) in enumerate(DBINS) if lo <= e['d'] < hi)
                C[('shot_d', b)] += 1
                C[('shot_cr', e.get('cr', 0))] += 1
                C[('shot_w', wclass(e.get('wpn') or e.get('wk')))] += 1
        # ── попадания: только пулей, свежий выстрел стрелка
        shooter_of = {}
        for e in evs:
            if e['ev'] != 'hit' or e.get('gren'):
                continue
            ts = shots.get(e.get('who'))
            if not ts:
                continue
            i = bisect.bisect_right(ts, e['t'])
            if i == 0 or e['t'] - ts[i - 1] > 500:
                continue
            C['hit'] += 1
            first.setdefault('hit', e['t'])
            d = e.get('d', 0)
            b = next(i for i, (lo, hi) in enumerate(DBINS) if lo <= d < hi)
            C[('hit_d', b)] += 1
            R['dmg'].append(e.get('amount', 0))
            C[('bone', e.get('bone', -1))] += 1
            hits_on[e['npc']] += 1
            shooter_of[(e['npc'], e['t'])] = e.get('who')
        # поза стрелка в момент попадания — по ближайшему выстрелу
        shot_cr, shot_w = {}, {}
        for e in evs:
            if e['ev'] == 'shot':
                shot_cr[(e['npc'], e['t'])] = e.get('cr', 0)
                shot_w[(e['npc'], e['t'])] = wclass(e.get('wpn') or e.get('wk'))
        for e in evs:
            if e['ev'] == 'hit' and not e.get('gren') and e.get('who') in shots:
                ts = shots[e['who']]
                i = bisect.bisect_right(ts, e['t'])
                if i and e['t'] - ts[i - 1] <= 500:
                    C[('hit_cr', shot_cr.get((e['who'], ts[i - 1]), 0))] += 1
                    C[('hit_w', shot_w.get((e['who'], ts[i - 1]), '?'))] += 1
        # ── смерти: пуль до смерти, раненые перед смертью
        for e in evs:
            if e['ev'] == 'death':
                first.setdefault('death', e['t'])
                if not e.get('gren'):
                    R['hits_to_kill'].append(hits_on[e['npc']])
                P = pos.get(e['npc'], [])
                C['death'] += 1
                if any(p[8] for p in P):
                    C['death_wnd'] += 1
        # ── потеря здоровья за одну пулю: окно двух npc_pos, в нём ровно одна пуля (склеенная), жертва не умерла
        hit_t = collections.defaultdict(list)
        for e in evs:
            if e['ev'] == 'hit' and not e.get('gren'):
                hit_t[e['npc']].append(e['t'])
        for npc, P in pos.items():
            H = hit_t.get(npc)
            if not H:
                continue
            for a, b in zip(P, P[1:]):
                if b[0] - a[0] > 700 or b[9] <= 0:
                    continue
                n = sum(1 for t in H if a[0] < t <= b[0])
                if n == 1 and a[9] - b[9] > 0.002:
                    R['hp_loss'].append((a[9] - b[9]) * HP_SCALE)
        # ── движение и доворот по npc_pos
        for npc, P in pos.items():
            for a, b in zip(P, P[1:]):
                dt = (b[0] - a[0]) / 1000
                if not 0.3 <= dt <= 0.8:
                    continue
                v = math.hypot(b[1] - a[1], b[2] - a[2]) / dt
                if v > 12:                      # телепорт / спавн
                    continue
                R['v_cr' if a[5] else 'v_st'].append(v)
                la, lb = math.hypot(a[3], a[4]), math.hypot(b[3], b[4])
                if la > 0.5 and lb > 0.5:
                    c = (a[3] * b[3] + a[4] * b[4]) / (la * lb)
                    ang = math.degrees(math.acos(max(-1, min(1, c))))
                    if ang > 5:
                        R['turn'].append(ang / dt)
                if b[8] and not a[8]:
                    C['wnd_enter'] += 1
            C['pos'] += len(P)
            C['pos_wnd'] += sum(1 for p in P if p[8])
        # ── обнаружение: первое bsee=1 на врага — дистанция до него
        for npc, P in pos.items():
            seen = set()
            for p in P:
                if p[6] and p[7] not in seen and p[7] in pos:
                    seen.add(p[7])
                    E = pos[p[7]]
                    k = min(range(len(E)), key=lambda j: abs(E[j][0] - p[0]))
                    if abs(E[k][0] - p[0]) < 700:
                        R['detect_d'].append(math.hypot(E[k][1] - p[1], E[k][2] - p[2]))
        # ── ритм очередей
        for npc, ts in shots.items():
            run = 1
            for a, b in zip(ts, ts[1:]):
                g = (b - a) / 1000
                if g < 0.25:
                    R['cyc'].append(g)
                    run += 1
                else:
                    R['burst'].append(run)
                    if g < 5:
                        R['pause'].append(g)
                    run = 1
            R['burst'].append(run)
        # ── хронология матча
        for k in ('shot', 'hit', 'death'):
            if k in first:
                R['first_' + k].append((first[k] - m['t0']) / 1000)
        if 't1' in m:
            R['dur'].append((m['t1'] - m['t0']) / 1000)
        C['match'] += 1
    return R, C


def pct(a, b):
    return '—' if not b else f'{100 * a / b:.1f}% ({a}/{b})'


def report(G, T):
    (RG, CG), (RT, CT) = G, T
    rows = []

    def row(name, g, t):
        rows.append((name, g, t))

    row('матчей', str(CG['match']), str(CT['match']))
    row('выстрелов / попаданий пулей', f"{CG['shot']} / {CG['hit']}", f"{CT['shot']} / {CT['hit']}")
    row('**попадание на выстрел**', pct(CG['hit'], CG['shot']), pct(CT['hit'], CT['shot']))
    for i, (lo, hi) in enumerate(DBINS):
        nm = f'  дистанция {lo}–{hi if hi < 1e8 else "…"} м'
        row(nm, pct(CG[('hit_d', i)], CG[('shot_d', i)]), pct(CT[('hit_d', i)], CT[('shot_d', i)]))
    row('  доля выстрелов по дистанциям',
        ' / '.join(f"{100 * CG[('shot_d', i)] / max(1, CG['shot']):.0f}" for i in range(len(DBINS))),
        ' / '.join(f"{100 * CT[('shot_d', i)] / max(1, CT['shot']):.0f}" for i in range(len(DBINS))))
    row('  стрелок стоя', pct(CG[('hit_cr', 0)], CG[('shot_cr', 0)]), pct(CT[('hit_cr', 0)], CT[('shot_cr', 0)]))
    row('  стрелок сидя', pct(CG[('hit_cr', 1)], CG[('shot_cr', 1)]), pct(CT[('hit_cr', 1)], CT[('shot_cr', 1)]))
    row('  выстрелов сидя', pct(CG[('shot_cr', 1)], CG['shot']), pct(CT[('shot_cr', 1)], CT['shot']))
    for w in ('w_rifle', 'w_smg', 'w_pistol', 'w_shotgun', 'w_sniper', '?'):
        if CG[('shot_w', w)] or CT[('shot_w', w)]:
            row(f'  {w}', pct(CG[('hit_w', w)], CG[('shot_w', w)]), pct(CT[('hit_w', w)], CT[('shot_w', w)]))
    row('урон пули до множителя кости: p10 / медиана / p90',
        f"{q(RG['dmg'], .1):.0f} / {q(RG['dmg'], .5):.0f} / {q(RG['dmg'], .9):.0f}",
        f"{q(RT['dmg'], .1):.0f} / {q(RT['dmg'], .5):.0f} / {q(RT['dmg'], .9):.0f}")
    row('потеря здоровья за пулю (×111): p10 / медиана / p90',
        f"{q(RG['hp_loss'], .1):.0f} / {q(RG['hp_loss'], .5):.0f} / {q(RG['hp_loss'], .9):.0f}",
        f"{q(RT['hp_loss'], .1):.0f} / {q(RT['hp_loss'], .5):.0f} / {q(RT['hp_loss'], .9):.0f}")
    row('пуль до смерти: p25 / медиана / p75',
        f"{q(RG['hits_to_kill'], .25)} / {q(RG['hits_to_kill'], .5)} / {q(RG['hits_to_kill'], .75)}",
        f"{q(RT['hits_to_kill'], .25)} / {q(RT['hits_to_kill'], .5)} / {q(RT['hits_to_kill'], .75)}")
    bones = sorted({k[1] for k in CG if isinstance(k, tuple) and k[0] == 'bone'}, key=str)
    row('кости попаданий (id: доля)', ', '.join(f"{b}: {100 * CG[('bone', b)] / max(1, CG['hit']):.0f}%" for b in bones),
        'всегда 1 (кости нет)')
    row('ранен перед смертью', pct(CG['death_wnd'], CG['death']), pct(CT['death_wnd'], CT['death']))
    row('скорость стоя: стоит (<0.3 м/с)', pct(sum(v < .3 for v in RG['v_st']), len(RG['v_st'])),
        pct(sum(v < .3 for v in RT['v_st']), len(RT['v_st'])))
    for nm, key in (('стоя', 'v_st'), ('сидя', 'v_cr')):
        mg = [v for v in RG[key] if v >= .3]
        mt = [v for v in RT[key] if v >= .3]
        row(f'  в движении {nm}: медиана / p90 / p99, м/с',
            f'{q(mg, .5):.2f} / {q(mg, .9):.2f} / {q(mg, .99):.2f}', f'{q(mt, .5):.2f} / {q(mt, .9):.2f} / {q(mt, .99):.2f}')
    row('доворот (>5°): медиана / p90 / p99, °/с',
        f"{q(RG['turn'], .5):.0f} / {q(RG['turn'], .9):.0f} / {q(RG['turn'], .99):.0f}",
        f"{q(RT['turn'], .5):.0f} / {q(RT['turn'], .9):.0f} / {q(RT['turn'], .99):.0f}")
    row('обнаружение: p25 / медиана / p75, м',
        f"{q(RG['detect_d'], .25):.0f} / {q(RG['detect_d'], .5):.0f} / {q(RG['detect_d'], .75):.0f}",
        f"{q(RT['detect_d'], .25):.0f} / {q(RT['detect_d'], .5):.0f} / {q(RT['detect_d'], .75):.0f}")
    row('очередь: медиана / p90 патронов', f"{q(RG['burst'], .5)} / {q(RG['burst'], .9)}",
        f"{q(RT['burst'], .5)} / {q(RT['burst'], .9)}")
    row('темп внутри очереди, выстр/с (медиана)', f"{1 / q(RG['cyc'], .5):.1f}" if RG['cyc'] else '—',
        f"{1 / q(RT['cyc'], .5):.1f}" if RT['cyc'] else '—')
    row('пауза между очередями: медиана / p90, с', f"{q(RG['pause'], .5):.2f} / {q(RG['pause'], .9):.2f}",
        f"{q(RT['pause'], .5):.2f} / {q(RT['pause'], .9):.2f}")
    for k, nm in (('first_shot', 'первый выстрел'), ('first_hit', 'первое попадание'), ('first_death', 'первая смерть'),
                  ('dur', 'длина матча')):
        row(f'{nm}: медиана, с', f"{q(RG[k], .5):.0f}", f"{q(RT[k], .5):.0f}")
    print('| замер | игра | двойник |\n|---|---|---|')
    for r in rows:
        print('| ' + ' | '.join(r) + ' |')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', action='append', required=True)
    ap.add_argument('--twin', action='append', required=True)
    a = ap.parse_args()
    G = measure(load([f for p in a.game for f in files(p)]))
    T = measure(load([f for p in a.twin for f in files(p)]))
    report(G, T)
