#!/usr/bin/env python3
"""
Таблицы оружия из конфигов Anomaly (17.11.2026): вводные боя — что у кого в руках и чего оно стоит.

Выход (рядом со скриптом, data/):
  weapons.csv   — ствол: класс, урон, скорострельность, разброс, отдача, магазин, дальность, вес, цена, износ, патроны
  ammo.csv      — патрон: множители урона/бронебойности/разброса/дальности, дробь, цена
  loadouts.csv  — группировка × ранг × слот → какие стволы выдаются (npc_loadouts_*.ltx)
Варианты одного ствола (_camo, _custom, апгрейды) идут отдельными строками, base — секция-родитель.

Поля движка (по исходнику, xrGame/Weapon*.cpp): hit_power — урон пули × k_hit патрона; fire_dispersion_base —
разброс ствола (градусы) × k_disp патрона × PDM_* (поза/движение); cam_* — отдача камеры (у NPC её нет, она игрока);
rpm — выстр/мин; condition_shot_dec — износ за выстрел.
Использование: python3 weapons/bake_weapon_table.py
"""
import csv
import glob
import os
import re

from ltx import CONFIGS, get, load_sections

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'data')
KINDS = ('w_rifle', 'w_smg', 'w_pistol', 'w_shotgun', 'w_sniper', 'w_explosive')

WPN_KEYS = ['kind', 'ef_weapon_type', 'hit_power', 'hit_impulse', 'hit_type', 'bullet_speed', 'fire_distance', 'rpm',
            'fire_modes', 'ammo_mag_size', 'fire_dispersion_base', 'PDM_disp_base', 'PDM_disp_vel_factor',
            'PDM_disp_accel_factor', 'PDM_disp_crouch', 'PDM_disp_crouch_no_acc', 'cam_dispersion',
            'cam_dispersion_inc', 'cam_max_angle', 'cam_relax_speed', 'cam_step_angle_horz', 'zoom_cam_dispersion',
            'crosshair_inertion', 'inv_weight', 'cost', 'condition_shot_dec', 'misfire_probability',
            'misfire_start_condition', 'silencer_status', 'scope_status', 'grenade_launcher_status', 'ammo_class']
AMMO_KEYS = ['k_hit', 'k_ap', 'k_disp', 'k_dist', 'k_impulse', 'k_air_resistance', 'buck_shot', 'impair',
             'box_size', 'inv_weight', 'cost', 'tracer']
RANKS = ['novice', 'trainee', 'experienced', 'professional', 'veteran', 'expert', 'master', 'legend']


def first_num(v):
    """hit_power = 0.5, 0.5, 0.5, 0.5 (по сложностям) → первое число."""
    if v is None:
        return ''
    return v.split(',')[0].strip()


def weapons(S):
    rows = []
    for sec in sorted(S):
        if not sec.startswith('wpn_') or sec.endswith('_hud') or get(S, sec, 'kind') not in KINDS:
            continue
        if get(S, sec, 'cost') is None or get(S, sec, 'hit_power') is None:
            continue
        r = {'section': sec, 'base': (S[sec]['_par'] or [''])[0]}
        for k in WPN_KEYS:
            v = get(S, sec, k)
            r[k] = first_num(v) if k == 'hit_power' else (v or '')
        r['ammo_class'] = ' '.join(a.strip() for a in r['ammo_class'].split(',') if a.strip())
        rows.append(r)
    return rows


def ammo(S):
    rows = []
    for sec in sorted(S):
        if sec.startswith('ammo_') and get(S, sec, 'k_hit') is not None and get(S, sec, 'box_size') is not None:
            rows.append({'section': sec, **{k: get(S, sec, k) or '' for k in AMMO_KEYS}})
    return rows


def loadouts():
    """[dolg_novice] primary = duty_novice_primary → строки списка (wpn_x[:флаги]). Наследование через ltx.get."""
    L = load_sections('items/settings/npc_loadouts/*.ltx')
    rows = []
    for sec in sorted(L):
        m = re.match(r'^([a-z_]+?)_(' + '|'.join(RANKS) + r')$', sec)
        if not m:
            continue
        faction, rank = m.groups()
        for slot in ('primary', 'secondary', 'extra'):
            lst = get(L, sec, slot)
            if not lst or lst not in L:
                continue
            items = list_items(lst)
            for w in items:
                rows.append({'faction': faction, 'rank': rank, 'slot': slot, 'list': lst, 'weapon': w})
    return rows


def list_items(lst):
    """Секции-списки — голые строки без «=»: ltx.load_sections их не берёт, читаем сами."""
    out = []
    for f in glob.glob(f'{CONFIGS}/items/settings/npc_loadouts/*.ltx'):
        cur = None
        for line in open(f, encoding='latin-1'):
            line = line.split(';')[0].strip()
            m = re.match(r'^\[([^\]]+)\]', line)
            if m:
                cur = m.group(1)
                continue
            if cur == lst and line and '=' not in line:
                out.append(line.split(':')[0].strip())
    return out


def write(name, rows):
    path = os.path.join(OUT, name)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f'{len(rows):5d} строк → {os.path.relpath(path, HERE)}')


def main():
    os.makedirs(OUT, exist_ok=True)
    S = load_sections('items/weapons/**/*.ltx')
    write('weapons.csv', weapons(S))
    write('ammo.csv', ammo(S))
    write('loadouts.csv', loadouts())


if __name__ == '__main__':
    main()
