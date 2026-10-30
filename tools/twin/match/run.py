#!/usr/bin/env python3
"""
Раннер матчей (20.10.2026): матч из JSON → живая Anomaly → кусок trace + оценка.

Нужно: запущен tools/twin/server.py (он пишет команды игре), игра на уровне матча.
Раннер говорит с игрой тем же протоколом, что творческий режим: POST /cmd → varka_cmd.script,
ответы (cmd_ok / cmd_fail / match_end) читает прямо из файла trace.

Формат матча (matches/*.json):
  {
    "id": "l07_square",                  имя матча
    "level": "l07_military",             уровень (запечённый в levels/); "here" — где сейчас стоит игра
                                         (спек на смартах годится для любой локи)
    "limit_s": 300,                      лимит времени
    "zone": {"x": 40, "z": 10, "r": 15}, точка-задача: держит тот, у кого в радиусе только свои
    "spectator": {"x": 30, "z": 40},     куда поставить игрока смотреть (рядом — иначе отряды уйдут в офлайн)
    "ghost": true,                       отряды нейтральны к игроку
    "grenades": 1,                       РГД-5 каждому бойцу (24.10; можно и в отряде: "grenades" рядом с "n")
    "approach": "sprint",                темп подхода к точке: walk (по умолчанию) | run | sprint (до 40 м от точки)
    "speed": 1,                          time_factor на время матча
    "hour": 10,                          перед серией перевести часы игры до этого часа (бои при свете)
    "cvars": {"ai_aim_fire_angle": 0.087}, консольные ai_* на серию (опыт над ванилью); после — вернуть как было
    "sides": {
      "A": {"director": "shturm",        пресет | "off" (глушит ТОЛЬКО дирижёра) | "default" | "random"
            "stack": "vanilla",          25.10: сторона «чистая ваниль» — VARKA её бойцов не трогает вовсе
                                         (varka_vanilla.script; общими остаются мир и тело). По умолчанию "varka"
            "start": "advance",          advance — мягко идти к точке (бой важнее), hold — стоять
            "squads": [{"faction": "freedom", "tier": "advanced", "n": 4, "at": {"x": -20, "z": 0}}]},
      "B": {...}
    }
  }
  faction: freedom duty stalker bandit army monolith csky ecolog greh isg killer renegade;  tier: novice advanced veteran
           (killer — наёмники, отряды merc_sim_squad_*; renegade — ренегаты)
  Точки — в метрах игры (x, z), как во вьювере под мышью; раннер сам находит ноду.

  Разброс (каждый матч заново, итог пишется в results.jsonl → setup):
    "faction": ["freedom","duty"]  "tier": "random" или список   "n": [3, 6]   "at": [{x,z}, {x,z}, ...]
    "swap": true — с вероятностью ½ стороны меняются местами спавна
    "mirror": true — 30.10: матчи парами (1–2, 3–4 …), во втором стороны меняются точками; пара = AB/BA
    в отряде "member": "sim_default_stalker_2", "rank": "experienced" — один профиль и ровный ранг (стенд этюда);
    "kit": {..., "visual": "actors\\stalker_neutral\\stalker_neutral_2"} — одна модель (= одна броня)
    "alternate": true — 25.10: в чётных матчах стороны меняются группировками (ваниль/VARKA играют обеими)
    "even": true — ранг и численность поровну обеим сторонам, все сочетания по кругу (ровная раздача за серию)
    "matchup": "random" — фракции и ранги сторон выбираются по правилам пар (pick_matchup): только
                          ВРАГИ по отношениям группировок (≤ -1000 в обе стороны; игра отвечает на
                          команду rel, без игры — базовая матрица game_relations.ltx); ИИГ против
                          всех, кроме Монолита и Греха, — на ступень ниже по рангу
    "matchup": "ranks", "balance": 3 — бои по рангам (21.10): пара врагов, у стороны своя численность
                          (n: [1, 4]) и один из 8 рангов (новичок … легенда); состав, где одна сторона
                          сильнее другой больше чем в balance раз, отбрасывается. Сила — power()
  Вся локация (смарт-террейны — места, куда ходит симуляция; список игра выгружает сама, кэш levels/<уровень>_smarts.json):
    "zone": {"smart": "random", "r": 15}       точка матча — случайный смарт (или имя, или список имён)
    "zone": {"smart": "cycle", "r": 15}        24.10: полный круг — все смарты уровня по разу в перемешанном порядке,
                                               потом новый круг (match/zone_cycle.json; случайный выбор давал 1…12 раз)
    "zone": {..., "defend": [смарты]}          выпал смарт из списка — сторона A рождается на точке (оборона), B атакует
    "at": {"smart_ring": [50, 120]}            спавн — смарт на таком расстоянии от точки; у B — с другой стороны
    "spectator": "zone"                         игрок встаёт на точку (с g_god on — безопасно)
    "spectator": {"aside": 30}                  игрок сбоку от боя: в 30 м от точки поперёк линии A→B
                                                (на точке он «свой на линии» для ванильного rx_ff)
    "camera": {"up": 18, "back": 25}            если ты в деморекорде (demo_record 1): свободная камера
                                                переезжает к точке — выше на up, отступив на back, смотрит на точку
  Перед матчем площадка чистится: clear_r м вокруг точки (по умолчанию 150) — чужие отряды без сюжетных
  меток и трупы убираются (сюжетные NPC остаются).

Использование:
  python3 match/run.py matches/l07_square.json            один матч
  python3 match/run.py matches/l07_square.json --n 20     серия (датасет): игра крутит матчи сама
  python3 match/run.py matches/l07_square.json --dry      только показать команды

Уборка: --cleanup none | clear | clear2 | vanish | all (через запятую). По умолчанию all (21.10): краш 20.10
  оказался не от уборки (свои id в боевом планировщике), а выжившие прошлого матча влезали в следующий.
  clear  — чистка площадки перед спавном (чужие отряды, трупы, брошенное оружие)
  clear2 — повторная чистка перед стартом (только чужие отряды)
  vanish — убрать выживших после матча (без убийства: перевести в офлайн → удалить)
  none   — ничего не убирать, выжившие остаются на старом месте
"""
import argparse
import glob
import json
import math
import os
import random
import re
import sys
import time
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
TWIN = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import score as scoring  # noqa: E402

TRACE = os.environ.get('VARKA_TRACE', '/mnt/games/ANOMALY_DEV/appdata/logs/varka_trace.jsonl')
SERVER = os.environ.get('VARKA_SERVER', 'http://localhost:8766')
RUNS = os.path.join(HERE, 'runs')
RESULTS = os.path.join(HERE, 'results.jsonl')
RANDOM_DIRECTORS = ['shturm', 'greh', 'front', 'bound', 'cover', 'off']
RUN_STAMP = time.strftime('%H%M%S')
TIERS = ['novice', 'advanced', 'veteran']


def pick(v, rng, pool=None):
    """Значение из спека: список — случайный элемент, "random" — из pool, иначе как есть."""
    if v == 'random' and pool:
        return rng.choice(pool)
    if isinstance(v, list):
        return rng.choice(v)
    return v


def load_smarts(game, lvl, name):
    """Смарт-террейны уровня: из кэша или выгрузкой из игры (команда smarts)."""
    path = os.path.join(TWIN, 'levels', name + '_smarts.json')
    if os.path.exists(path):
        return json.load(open(path, encoding='utf-8'))
    if game.dry:
        raise SystemExit(f'нет {path} — нужен один запуск с игрой, она выгрузит смарты')
    since = game.mark()
    game.call('smarts')
    time.sleep(1)
    game.read()
    out = [{'name': e['name'], 'x': e['x'], 'z': e['z'], 'vid': e['vid']}
           for e in game.buf[since:] if e.get('ev') == 'smart' and e.get('level') == name]
    json.dump(out, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'  смартов на {name}: {len(out)} → {os.path.relpath(path, TWIN)}')
    return out


CYCLE_FILE = os.path.join(HERE, 'zone_cycle.json')


def cycle_next(level, names, rng, save=True):
    """Полный круг по смартам уровня: перемешанный порядок, по разу каждый, потом новый круг. Состояние — в файле,
    чтобы круг продолжался между запусками раннера. save=False (--dry) — не двигать круг."""
    try:
        st = json.load(open(CYCLE_FILE))
    except (OSError, ValueError):
        st = {}
    c = st.get(level)
    if not c or sorted(c.get('order', [])) != sorted(names) or c.get('i', 0) >= len(c['order']):
        order = list(names)
        rng.shuffle(order)
        c = {'order': order, 'i': 0, 'round': (c or {}).get('round', 0) + 1}
    name = c['order'][c['i']]
    c['i'] += 1
    st[level] = c
    if save:
        json.dump(st, open(CYCLE_FILE, 'w'), ensure_ascii=False, indent=1)
    return name


def place(spec, setup, smarts, rng, lvl=None, dry=False):
    """Точка матча и места спавна, если они заданы через смарты. Меняет setup на месте."""
    zone = dict(spec['zone'])
    if 'smart' in zone:
        names = [s['name'] for s in smarts]
        want = zone['smart']
        pick_from = names if want in ('random', 'cycle') else (want if isinstance(want, list) else [want])
        if want == 'cycle' and lvl:
            pick_name = cycle_next(lvl.name, names, rng, save=not dry)
        else:
            pick_name = rng.choice(pick_from)
        sm = next(s for s in smarts if s['name'] == pick_name)
        zone.update(x=sm['x'], z=sm['z'], name=sm['name'])
    # оборона (23.10): точка из списка zone.defend — сторона A рождается на ней (тоннель Агропрома 6_4: у костра),
    # B идёт с кольца. Случайно выпавший тоннель без этого — спавн наверху, дороги вниз не нашли, тайм-аут (011929-5).
    if zone.get('name') and zone['name'] in spec['zone'].get('defend', []):
        for q in setup['A']['squads']:
            q['at'] = {'x': zone['x'], 'z': zone['z'], 'smart': zone['name']}
        zone['defend'] = True
    ang_a = None
    for side in ('A', 'B'):
        for q in setup[side]['squads']:
            ring = isinstance(q['at'], dict) and q['at'].get('smart_ring')
            if not ring:
                continue
            cands = []
            for sm in smarts:
                dx, dz = sm['x'] - zone['x'], sm['z'] - zone['z']
                d = math.hypot(dx, dz)
                if ring[0] <= d <= ring[1]:
                    a = math.atan2(dz, dx)
                    # сторона B — с другой стороны от точки (угол от A больше 90°)
                    if side == 'B' and ang_a is not None and abs((a - ang_a + math.pi) % (2 * math.pi) - math.pi) < math.pi / 2:
                        continue
                    cands.append((sm, a))
            if cands:
                sm, a = rng.choice(cands)
                q['at'] = {'x': sm['x'], 'z': sm['z'], 'smart': sm['name']}
            elif lvl:
                # смартов на таком кольце нет (край карты) — точка на кольце по навмешу,
                # у B — напротив A с разбросом ±60°
                for _ in range(60):
                    a = rng.uniform(-math.pi, math.pi) if (side == 'A' or ang_a is None) \
                        else ang_a + math.pi + rng.uniform(-math.pi / 3, math.pi / 3)
                    d = rng.uniform(*ring)
                    x, z = zone['x'] + d * math.cos(a), zone['z'] + d * math.sin(a)
                    # 23.10: не дальше NEAR_SMART от какого-нибудь смарта — иначе спавн за периметром (011929-5)
                    near = not smarts or min(math.hypot(sm['x'] - x, sm['z'] - z) for sm in smarts) <= NEAR_SMART
                    if near and lvl.has_node(x, z):
                        q['at'] = {'x': x, 'z': z, 'smart': None}
                        break
                else:
                    raise RuntimeError(f"нет места для спавна стороны {side} в {ring} м от точки")
            else:
                raise RuntimeError(f"нет смартов в {ring} м от точки {zone.get('name', '')} для стороны {side}")
            if side == 'A':
                ang_a = a
    return zone


NEAR_SMART = 70  # м: случайная точка спавна на кольце — не дальше от ближайшего смарта


def aside_point(zone, setup, dist, lvl):
    """Место зрителя сбоку от боя: перпендикуляр к линии A→B через точку матча.
    Ночь 21.10: игрок на самой точке — «свой на линии» для rx_ff, 15% блокировок огня."""
    a, b = setup['A']['squads'][0]['at'], setup['B']['squads'][0]['at']
    dx, dz = b['x'] - a['x'], b['z'] - a['z']
    n = math.hypot(dx, dz) or 1
    px, pz = -dz / n, dx / n
    for d in (dist, dist * 0.8, dist * 1.25, dist * 0.6, dist * 1.5):
        for side in (1, -1):
            x, z = zone['x'] + side * px * d, zone['z'] + side * pz * d
            if lvl.has_node(x, z):
                return x, z
    return zone['x'], zone['z']


FACTIONS = ['stalker', 'bandit', 'army', 'freedom', 'duty', 'csky', 'ecolog', 'monolith', 'greh', 'isg',
            'killer', 'renegade']
COMMUNITY = {'duty': 'dolg'}         # имя в спеке → группировка в игре (остальные совпадают)
SQUAD_PREFIX = {'killer': 'merc'}    # имя в спеке → префикс секции отряда <префикс>_sim_squad_<ранг>
ENEMY = -1000                        # game_relations.script: ENEMIES
RELATIONS_LTX = '/mnt/games/ANOMALY_DEV/tools/_unpacked/configs/creatures/game_relations.ltx'
RELATIONS = {}                       # (группировка, группировка) → отношение; заполняет load_relations


def relations_from_ltx():
    """Базовая матрица из конфига (такой она бывает в начале новой игры)."""
    names, rel = [], {}
    for line in open(RELATIONS_LTX, encoding='latin-1'):
        line = line.split(';')[0]
        if line.strip().startswith('communities') and '=' in line and not names:
            parts = [p.strip() for p in line.split('=', 1)[1].split(',')]
            names = parts[0::2]
        elif '=' in line and names:
            row, vals = line.split('=', 1)
            vals = [v.strip() for v in vals.split(',') if v.strip()]
            if row.strip() in names and len(vals) == len(names):
                for col, v in zip(names, vals):
                    rel[(row.strip(), col)] = int(v)
    return rel


def load_relations(game):
    """Отношения из живой игры (в Anomaly они меняются по ходу игры); без игры — из конфига."""
    comms = [COMMUNITY.get(f, f) for f in FACTIONS]
    base = relations_from_ltx()
    if game.dry:
        RELATIONS.update(base)
        return 'конфиг'
    try:
        info = game.call('rel', *comms)
    except (RuntimeError, TimeoutError) as e:   # старый varka_cmd без rel — конфиг
        print(f'  отношения: игра не ответила ({e}) — беру game_relations.ltx')
        RELATIONS.update(base)
        return 'конфиг'
    for item in info.split(';'):
        pair, v = item.rsplit(':', 1)
        a, b = pair.split('>')
        RELATIONS[(a, b)] = int(float(v))
    diff = [f'{a}>{b} {base.get((a, b))}→{v}' for (a, b), v in RELATIONS.items() if base.get((a, b)) != v]
    if diff:
        print('  отношения отличаются от конфига: ' + ', '.join(sorted(diff)))
    return 'игра'


def enemies(fa, fb):
    ca, cb = COMMUNITY.get(fa, fa), COMMUNITY.get(fb, fb)
    return RELATIONS.get((ca, cb), 0) <= ENEMY and RELATIONS.get((cb, ca), 0) <= ENEMY


def enemy_pairs():
    return [(a, b) for i, a in enumerate(FACTIONS) for b in FACTIONS[i + 1:] if enemies(a, b)]


def pick_matchup(rng):
    """Пара (фракция, ранг) для A и B: только враги по отношениям группировок (21.10) + ранги ИИГ."""
    pairs = enemy_pairs()
    if not pairs:
        raise RuntimeError('нет ни одной пары врагов — отношения не загружены?')
    while True:
        fa, fb = rng.choice(pairs)
        if rng.random() < 0.5:
            fa, fb = fb, fa
        ta, tb = rng.randrange(3), rng.randrange(3)
        for me, other, set_me in ((fa, fb, 'a'), (fb, fa, 'b')):
            if me == 'isg' and other not in ('monolith', 'greh'):
                t_other = tb if set_me == 'a' else ta
                if t_other == 0:
                    break                                # ниже новичков некуда — другая пара
                if set_me == 'a':
                    ta = t_other - 1
                else:
                    tb = t_other - 1
        else:
            return (fa, TIERS[ta]), (fb, TIERS[tb])


# ---------- бои по рангам (21.10): 1–4 на 1–4, перевес — да, избиение — нет ----------

RANKS = ['novice', 'trainee', 'experienced', 'professional', 'veteran', 'expert', 'master', 'legend']
RANK_VALUE = [1750, 5000, 7750, 10500, 13250, 16000, 22250, 30000]  # середины полос rating (game_relations.ltx)
RANK_STEP = 1.3      # вес бойца: ступень ранга сильнее прошлой в 1.3 раза (новичок 1 … легенда 6.3)
BALANCE = 3          # сильная сторона сильнее слабой не больше чем во столько раз (спек: "balance")
UNPACKED = '/mnt/games/ANOMALY_DEV/tools/_unpacked/configs'
PROFILES = {}        # группировка → [(секция бойца, ранг от, ранг до)]; заполняет load_profiles


def power(rank, n):
    """Сила стороны: сумма весов бойцов × √численности. Числа давят, но не в квадрат: по Ланчестеру
    квадрат — когда все стреляют во всех сразу, а у нас укрытия и бой по очереди."""
    return n * RANK_STEP ** rank * math.sqrt(n)


def load_profiles():
    """Секции бойцов sim_default_<…>_<N>: группировка (spawn_sections) и полоса ранга профиля
    (character_desc). Профиль даёт костюм; оружие игра выдаёт по рангу, а ранг раннер ставит сам."""
    ranges = {}
    for fn in glob.glob(os.path.join(UNPACKED, 'gameplay', 'profiles', 'character_desc_*.xml')):
        t = open(fn, encoding='latin-1').read()
        c, r = re.search(r'<class>([^<]+)</class>', t), re.search(r'<rank min="(\d+)" max="(\d+)"', t)
        if c and r:
            ranges[c.group(1)] = (int(r.group(1)), int(r.group(2)))
    sec, cur = {}, None
    for fn in glob.glob(os.path.join(UNPACKED, 'creatures', 'spawn_sections_*.ltx')):
        for line in open(fn, encoding='latin-1'):
            line = line.split(';')[0].strip()
            m = re.match(r'\[(sim_default_[a-z]+_\d+)\](?::(\S+))?', line)
            if m:
                cur = sec[m.group(1)] = {'parent': m.group(2)}
            elif line.startswith('['):
                cur = None
            elif cur is not None and '=' in line:
                k, v = (s.strip() for s in line.split('=', 1))
                if k in ('community', 'character_profile'):
                    cur[k] = v
    for name, s in sec.items():
        comm = s.get('community') or sec.get(s.get('parent'), {}).get('community')
        prof = s.get('character_profile', name)
        if comm and prof in ranges:
            PROFILES.setdefault(comm, []).append((name, *ranges[prof]))


def profile_for(faction, rank):
    """Секция бойца, в чью полосу ранга попадает нужный; если ни в чью — ближайшая."""
    v = RANK_VALUE[rank]
    cands = PROFILES.get(COMMUNITY.get(faction, faction))
    if not cands:
        raise RuntimeError(f'нет профилей бойцов для {faction}')
    return min(cands, key=lambda p: (max(p[1] - v, v - p[2], 0), abs((p[1] + p[2]) / 2 - v)))[0]


def pick_ranked(spec, out, rng):
    """Бой по рангам: пара врагов, у каждой стороны своя численность и ранг. Составы, где одна сторона
    сильнее другой больше чем в balance раз, отбрасываем и тянем заново (4 легенды на новичка — не бой)."""
    fa, fb = rng.choice(enemy_pairs())
    if rng.random() < 0.5:
        fa, fb = fb, fa
    lim = spec.get('balance', BALANCE)
    ns = []
    for s in ('A', 'B'):
        n = spec['sides'][s]['squads'][0].get('n', [1, 4])
        ns.append(n if isinstance(n, list) else [n, n])
    while True:
        na, nb = rng.randint(*ns[0]), rng.randint(*ns[1])
        ra, rb = rng.randrange(len(RANKS)), rng.randrange(len(RANKS))
        pa, pb = power(ra, na), power(rb, nb)
        if max(pa, pb) / min(pa, pb) <= lim:
            break
    for q, f, r, n, p in ((out['A']['squads'][0], fa, ra, na, pa), (out['B']['squads'][0], fb, rb, nb, pb)):
        q.update(faction=f, tier='advanced', rank=RANKS[r], n=n, member=profile_for(f, r), power=round(p, 2))


EVEN_ORDER = []   # «even»: очередь сочетаний (ранг, численность), перемешанная блоками


def even_combo(spec, rng, idx):
    """Ровная раздача (23.10, юзер): все сочетания ранг × численность по кругу, блок за блоком в случайном порядке —
    за ночь каждого поровну, а не как выпадет. Обе стороны получают одно и то же."""
    lo, hi = spec['sides']['A']['squads'][0].get('n', [3, 5])
    t0 = spec['sides']['A']['squads'][0].get('tier', 'random')   # 29.10: ранг задан в спеке — по кругу только численность
    tiers = [t0] if t0 in TIERS else TIERS
    combos = [(t, n) for t in tiers for n in range(lo, hi + 1)]
    while len(EVEN_ORDER) < idx:
        block = combos[:]
        rng.shuffle(block)
        EVEN_ORDER.extend(block)
    return EVEN_ORDER[idx - 1]


def setup_of(spec, rng, idx=1):
    """Конкретный матч из спека с разбросом: кто, сколько, какого ранга, откуда."""
    out = {}
    for s in ('A', 'B'):
        side = spec['sides'][s]
        out[s] = {
            'director': pick(side.get('director', 'default'), rng, RANDOM_DIRECTORS),
            'stack': side.get('stack', 'varka'),
            'start': side.get('start', 'advance'),
            'squads': [{
                'faction': pick(q['faction'], rng),
                'tier': pick(q.get('tier', 'advanced'), rng, TIERS),
                'n': rng.randint(*q['n']) if isinstance(q.get('n'), list) else q.get('n', 4),
                'at': pick(q['at'], rng),
                'kit': q.get('kit'),
                **{k: q[k] for k in ('member', 'rank') if k in q},  # 30.10: стенд — один профиль и ровный ранг
            } for q in side['squads']],
        }
    if spec.get('matchup') == 'random':  # фракции и ранги — по правилам пар, поверх того, что в спеке
        (fa, ta), (fb, tb) = pick_matchup(rng)
        for q in out['A']['squads']:
            q['faction'], q['tier'] = fa, ta
        for q in out['B']['squads']:
            q['faction'], q['tier'] = fb, tb
    if spec.get('matchup') == 'ranks':
        pick_ranked(spec, out, rng)
    if spec.get('even'):   # ранг и численность — поровну обеим сторонам (поправка ИСГ из pick_matchup остаётся)
        tier, n = even_combo(spec, rng, idx)
        ta = tb = TIERS.index(tier)
        fa, fb = out['A']['squads'][0]['faction'], out['B']['squads'][0]['faction']
        if fa == 'isg' and fb not in ('monolith', 'greh') and ta > 0:
            ta -= 1
        if fb == 'isg' and fa not in ('monolith', 'greh') and tb > 0:
            tb -= 1
        for q in out['A']['squads']:
            q['tier'], q['n'] = TIERS[ta], n
        for q in out['B']['squads']:
            q['tier'], q['n'] = TIERS[tb], n
    if spec.get('alternate') and idx % 2 == 0:  # 25.10: группировки сторон меняются местами каждый второй матч
        for qa, qb in zip(out['A']['squads'], out['B']['squads']):
            qa['faction'], qb['faction'] = qb['faction'], qa['faction']
    # 30.10: зеркало во времени — матчи парами, во втором из пары стороны меняются точками спавна (AB/BA)
    flip = idx % 2 == 0 if spec.get('mirror') else spec.get('swap') and rng.random() < 0.5
    if flip:  # стороны меняются местами спавна
        a, b = out['A']['squads'], out['B']['squads']
        for qa, qb in zip(a, b):
            qa['at'], qb['at'] = qb['at'], qa['at']
    return out


# ---------- уровень: (x, z) → нода по запечённой картинке vid ----------

class Level:
    def __init__(self, name):
        self.name = name
        self.meta = json.load(open(os.path.join(TWIN, 'levels', name + '.json')))
        self.vid = Image.open(os.path.join(TWIN, 'levels', name + '_vid.png')).convert('RGB').load()
        # нижняя нода клетки — первый этаж (23.10: точка/спавн на крыше → отряд застревал на лестнице)
        g = os.path.join(TWIN, 'levels', name + '_ground.png')
        self.ground = Image.open(g).convert('RGB').load() if os.path.exists(g) else self.vid
        self.info = Image.open(os.path.join(TWIN, 'levels', name + '.png')).convert('RGBA').load()

    def y(self, x, z):
        """Высота верхней ноды в клетке (R подложки = высота в рамке уровня)."""
        m = self.meta
        i = min(max(round((x - m['box'][0]) / m['cell']), 0), m['w'] - 1)
        j = min(max(m['h'] - 1 - round((z - m['box'][2]) / m['cell']), 0), m['h'] - 1)
        return m['box'][1] + self.info[i, j][0] / 255 * (m['box'][4] - m['box'][1])

    def node(self, x, z, search=6, top=False):
        """Нода в клетке (x, z): нижняя (первый этаж), с top=True — верхняя (вид сверху)."""
        m = self.meta
        img = self.vid if top else self.ground
        i0 = round((x - m['box'][0]) / m['cell'])
        j0 = m['h'] - 1 - round((z - m['box'][2]) / m['cell'])
        for rad in range(search + 1):  # ближайшая клетка с нодой, кольцами
            for di in range(-rad, rad + 1):
                for dj in range(-rad, rad + 1):
                    if max(abs(di), abs(dj)) != rad:
                        continue
                    i, j = i0 + di, j0 + dj
                    if 0 <= i < m['w'] and 0 <= j < m['h']:
                        r, g, b = img[i, j]
                        k = (r << 16 | g << 8 | b) - 1
                        if k >= 0:
                            return k
        raise SystemExit(f'нет ноды рядом с x={x} z={z} — точка в стене или за краем уровня')

    def has_node(self, x, z):
        try:
            self.node(x, z, search=2)
            return True
        except SystemExit:
            return False


# ---------- связь с игрой ----------

class Game:
    def __init__(self, dry=False):
        self.dry = dry
        self.f = None
        self.buf = []
        if not dry:
            self.f = open(TRACE, 'rb')  # бинарно: перемотка на недописанную строку — в байтах
            self.f.seek(0, os.SEEK_END)

    def send(self, cmd, *args):
        args = [str(a) for a in args]
        if self.dry:
            print('  >', cmd, *args)
            return None
        req = urllib.request.Request(SERVER + '/cmd', data=json.dumps({'cmd': cmd, 'args': args}).encode(),
                                     headers={'Content-Type': 'application/json'})
        return json.loads(urllib.request.urlopen(req, timeout=5).read())['seq']

    def read(self):
        """Новые события trace с прошлого чтения (и копит их для куска матча)."""
        new = []
        if os.path.getsize(TRACE) < self.f.tell():  # игру перезапустили — trace начат заново
            self.f.seek(0)
        while True:
            line = self.f.readline()
            if not line:
                break
            if not line.endswith(b'\n'):          # строка дописывается прямо сейчас
                self.f.seek(-len(line), os.SEEK_CUR)
                break
            try:
                e = json.loads(line.decode('utf-8', 'replace'))
            except ValueError:
                continue
            new.append(e)
        self.buf += new
        return new

    def mark(self):
        """Отметка «с этого места»: ожидание просмотрит всё, что пришло после неё."""
        self.read()
        return len(self.buf)

    def wait(self, pred, timeout, what, since=None):
        # read() забирает из файла всё, что есть, пачкой. Событие, нужное следующему ожиданию,
        # могло прийти в пачке предыдущего — поэтому смотрим буфер от отметки, а не только новое.
        i = len(self.buf) if since is None else since
        t_end = time.time() + timeout
        while True:
            self.read()
            while i < len(self.buf):
                r = pred(self.buf[i])
                i += 1
                if r:
                    return r
            if time.time() >= t_end:
                raise TimeoutError(what)
            time.sleep(0.25)

    def call(self, cmd, *args, timeout=10):
        """Команда и ожидание ответа игры. Возвращает info из cmd_ok, иначе исключение."""
        since = None if self.dry else self.mark()
        seq = self.send(cmd, *args)
        if self.dry:
            return 'sq:%d' % random.randint(1000, 9999) if cmd == 'spawn' else 'dry'
        e = self.wait(lambda e: e if e.get('ev') in ('cmd_ok', 'cmd_fail') and e.get('seq') == seq else None,
                      timeout, f'игра не ответила на {cmd} (идёт ли игра? загружен ли varka_cmd?)', since)
        if e['ev'] == 'cmd_fail':
            raise RuntimeError(f"{cmd}: {e.get('info')}")
        return e.get('info', '')


# ---------- один матч ----------

CLEANUP = set()   # что из уборки включено (--cleanup)


def run_one(spec, lvl, game, rng, tag):
    setup = setup_of(spec, rng, tag)
    smarts = load_smarts(game, lvl, lvl.name) if ('smart' in spec['zone'] or any(
        isinstance(q.get('at'), dict) and 'smart_ring' in q['at']
        for s in ('A', 'B') for q in spec['sides'][s]['squads'])) else []
    zone = place(spec, setup, smarts, rng, lvl, dry=game.dry)
    zone_vid = lvl.node(zone['x'], zone['z'])
    sides, directors = {}, {}

    print(f"матч {spec['id']} #{tag}  {lvl.name}" + (f"  точка: {zone['name']}" if zone.get('name') else ''))
    sp = spec.get('spectator')
    eye = None  # где стоит зритель сбоку — туда же камера
    if sp == 'zone':
        game.call('tp', zone_vid)
    elif isinstance(sp, dict) and 'aside' in sp:
        eye = aside_point(zone, setup, sp['aside'], lvl)
        game.call('tp', lvl.node(*eye))
    elif sp:
        game.call('tp', lvl.node(sp['x'], sp['z']))
    cam = spec.get('camera', {'up': 18, 'back': 25})
    if cam:  # деморекорд: камера к точке матча (без деморекорда команда ничего не делает)
        zy = lvl.y(zone['x'], zone['z'])
        if eye:
            cx, cz = eye
        else:
            cx, cz = zone['x'], zone['z'] - cam.get('back', 25)
        game.call('cam', round(cx, 2), round(zy + cam.get('up', 18), 2), round(cz, 2),
                  round(zone['x'], 2), round(zy + 1, 2), round(zone['z'], 2))
    if sp and not game.dry:
        time.sleep(3)  # после переноса окрестность выходит в онлайн не сразу — иначе чистка её не видит
    if spec.get('speed'):
        game.call('time', spec['speed'])
    if 'clear' in CLEANUP:
        print('  площадка: ' + game.call('clear', zone_vid, spec.get('clear_r', 150)))

    born = None if game.dry else game.mark()  # отсюда ждём выхода отрядов в онлайн
    for s in ('A', 'B'):
        vanilla = setup[s].get('stack') == 'vanilla'
        directors[s] = 'vanilla' if vanilla else setup[s]['director']
        sides[s] = []
        for q in setup[s]['squads']:
            section = f"{SQUAD_PREFIX.get(q['faction'], q['faction'])}_sim_squad_{q.get('tier', 'advanced')}"
            vid = lvl.node(q['at']['x'], q['at']['z'])
            rank = (q['member'], RANK_VALUE[RANKS.index(q['rank'])]) if q.get('rank') else ()  # бой по рангам
            gren = q.get('grenades', spec.get('grenades', 0))  # 24.10: РГД-5 каждому бойцу (гранаты v2)
            if gren or vanilla:
                rank = (rank or ('-', '-')) + (gren,)
            if vanilla:  # 25.10: 8-й аргумент spawn — отряд «чистая ваниль» (метка до выхода в онлайн)
                rank = rank + (1,)
            kit = q.get('kit') or {}
            guns = ','.join(g for g in (kit.get('weapon'), kit.get('pistol')) if g)
            if guns:  # 29.10: 9-й аргумент — стволы стенда (выдаются на сервере, до онлайна)
                rank = (rank or ('-', '-')) + (gren,) if len(rank) < 3 else rank
                rank = rank + (1 if vanilla else 0,) if len(rank) < 4 else rank
                rank = rank + (guns,)
            info = game.call('spawn', section, vid, q.get('n', 4), 1 if spec.get('ghost', True) else 0, *rank)
            sides[s].append(int(info.split(':')[1]))
    every = sides['A'] + sides['B']
    desc = lambda s: ' + '.join(f"{q['faction']} {q.get('rank', q['tier'])} ×{q['n']}" for q in setup[s]['squads'])
    print(f"  A {directors['A']} [{desc('A')}] {sides['A']}   B {directors['B']} [{desc('B')}] {sides['B']}")
    pa, pb = setup['A']['squads'][0].get('power'), setup['B']['squads'][0].get('power')
    if pa:
        print(f"  сила A {pa} : B {pb}  (перевес ×{max(pa, pb) / min(pa, pb):.1f})")

    # все отряды должны выйти в онлайн, иначе стравить не получится
    if not game.dry:
        seen = set()

        def online(e):
            if e.get('ev') == 'npc_pos' and e.get('sq') in every:
                seen.add(e['sq'])
            return len(seen) == len(every)
        game.wait(online, 20, 'отряды не вышли в онлайн — поставь spectator ближе', born)

    for s in ('A', 'B'):
        if directors[s] == 'vanilla':
            continue  # дирижёра у ванили нет
        for sq in sides[s]:
            game.call('preset', f'sq:{sq}', directors[s])
    # 29.10: стенд этюда — "kit": {"community": "dolg", "weapon": "wpn_ak74", "pistol": "wpn_pm"}; группировка — тут, стволы — в spawn
    for s in ('A', 'B'):
        for q, sq in zip(setup[s]['squads'], sides[s]):
            kit = q.get('kit')
            if kit and kit.get('community'):
                vis = (kit['visual'],) if kit.get('visual') else ()
                print('  kit: ' + str(game.call('kit', f'sq:{sq}', kit['community'], *vis)))
    for a in sides['A']:
        for b in sides['B']:
            game.call('hostile', f'sq:{a}', f'sq:{b}')
    for s in ('A', 'B'):
        if setup[s]['start'] == 'advance':
            for sq in sides[s]:
                # 24.10: темп подхода — walk (как было) | run | sprint (спринт до 40 м от точки, дальше бег; экономия времени)
                game.call('order', f'sq:{sq}', 'move', zone_vid, 0, spec.get('approach', 'walk'))
        else:
            for sq in sides[s]:
                game.call('free', f'sq:{sq}')

    # вторая чистка: за время спавна могли подойти чужие (посты, патрули симуляции); свои — в keep
    if 'clear2' in CLEANUP:
        print('  перед стартом: ' + game.call('clear', zone_vid, spec.get('clear_r', 150), ','.join(map(str, every)), 'squads'))

    mid = f"{spec['id']}#{RUN_STAMP}-{tag}"   # уникально между запусками раннера
    begun = None if game.dry else game.mark()
    game.call('match_begin', mid, spec.get('limit_s', 300), zone_vid, zone.get('r', 15),
              ','.join(map(str, sides['A'])), ','.join(map(str, sides['B'])))
    if game.dry:
        return None

    try:
        game.wait(lambda e: e.get('ev') == 'match_end' and e.get('id') == mid,
                  spec.get('limit_s', 300) + 60, 'матч не кончился', begun)
    except TimeoutError:
        game.call('match_abort')
        game.wait(lambda e: e.get('ev') == 'match_end' and e.get('id') == mid, 10, 'match_abort не дошёл', begun)
    time.sleep(3)  # конец матча → выжившим запрещён подбор; даём событиям смерти и подбора отыграть
    game.read()

    if 'vanish' in CLEANUP:
        for sq in every:  # убрать выживших, чтобы следующий матч был чистым (без убийства: офлайн → удалить)
            try:
                game.call('vanish', f'sq:{sq}')
            except RuntimeError:
                pass
    if spec.get('speed'):
        game.call('time', 1)

    # кусок trace этого матча — датасет для двойника
    os.makedirs(RUNS, exist_ok=True)
    stamp = time.strftime('%Y%m%d_%H%M%S')
    where = f"_{lvl.name}" if spec.get('level', 'here') == 'here' else ''  # спек «здесь» играется на разных локах
    path = os.path.join(RUNS, f"{spec['id']}{where}_{stamp}_{tag}.jsonl")
    with open(path, 'w', encoding='utf-8') as f:
        for e in game.buf:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')
    game.buf = []

    r = scoring.score(scoring.load(path))
    r.update(directors=directors, setup=setup, zone=zone, run=os.path.relpath(path, HERE), spec=spec['id'],
             cvars=spec.get('cvars'), level=lvl.name)
    with open(RESULTS, 'a', encoding='utf-8') as f:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
    scoring.show(r)
    return r


def single_instance():
    """Второй раннер параллельно = две чистки и два матча на одной площадке (полигон 20.10). Не даём."""
    import fcntl
    f = open(os.path.join(HERE, '.runner.lock'), 'w')
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('раннер уже запущен в другом терминале — останови его (Ctrl+C) и запусти заново')
    return f


def series(spec, lvl, game, rng, args):
    """Матчи серии подряд; итоги — списком."""
    results, fails = [], 0
    for i in range(args.n):
        r = None
        try:
            for _ in range(10):  # точка у края карты, второй стороне негде встать — другая точка
                try:
                    r = run_one(spec, lvl, game, rng, i + 1)
                    break
                except RuntimeError as e:
                    if 'нет места' not in str(e):
                        raise
                    print(f'  {e} — другая точка')
            fails = 0
        except (RuntimeError, TimeoutError, OSError) as e:
            # один сбойный матч не роняет серию (ночной прогон); три подряд — игра, скорее всего, упала
            fails += 1
            print(f'  СБОЙ матча #{i + 1} ({fails} подряд): {e}')
            if fails >= 3:
                print('три сбоя подряд — серия остановлена (игра жива? сервер запущен?)')
                break
        if r:
            results.append(r)
        if i + 1 < args.n:
            time.sleep(args.pause)
    return results


def level_of(spec, game):
    """Уровень серии: из спека или "here" — спрашиваем игру, где она сейчас (команда level без имени)."""
    name = spec.get('level', 'here')
    if name != 'here':
        return name
    return 'l07_military' if game.dry else game.call('level')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('spec')
    ap.add_argument('--n', type=int, default=1, help='сколько матчей подряд')
    ap.add_argument('--pause', type=float, default=5, help='секунд между матчами')
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--cleanup', default='all', help='none | clear,clear2,vanish | all')
    args = ap.parse_args()
    CLEANUP.clear()
    CLEANUP.update({'clear', 'clear2', 'vanish'} if args.cleanup == 'all'
                   else {c for c in args.cleanup.split(',') if c and c != 'none'})
    print('уборка: ' + (', '.join(sorted(CLEANUP)) or 'выключена'))

    lock = None if args.dry else single_instance()  # noqa: F841 — держим файл открытым до конца
    spec = json.load(open(args.spec, encoding='utf-8'))
    rng = random.Random(args.seed)
    game = Game(args.dry)
    lvl = Level(level_of(spec, game))
    print('уровень: ' + lvl.name)
    if spec.get('matchup') in ('random', 'ranks'):
        src = load_relations(game)
        print(f'пары врагов ({src}): ' + ', '.join(f'{a}–{b}' for a, b in enemy_pairs()))
    if spec.get('matchup') == 'ranks':
        load_profiles()
        print(f"бои по рангам: перевес сил не больше ×{spec.get('balance', BALANCE)}; "
              f"профилей бойцов: {sum(map(len, PROFILES.values()))}")
    if 'hour' in spec:  # серия при свете: часы игры вперёд до этого часа (один раз)
        print('часы игры: ' + game.call('hour', spec['hour']))
    restore = {}
    for k, v in spec.get('cvars', {}).items():  # ответ «имя старое → новое»: старое вернём после серии
        info = game.call('cvar', k, v)
        print('консоль: ' + info)
        restore[k] = info.split()[1] if not args.dry else None
    try:
        results = series(spec, lvl, game, rng, args)
    finally:
        for k, v in restore.items():
            if v is not None:
                print('консоль назад: ' + game.call('cvar', k, v))
    if len(results) > 1:
        by = {}
        for r in results:
            by.setdefault(f"A {r['directors']['A']} vs B {r['directors']['B']}", []).append(r['score_a'])
        print('\nсерия:')
        for k, v in by.items():
            print(f'  {k}: матчей {len(v)}, средний счёт A {sum(v) / len(v):+.2f}')


if __name__ == '__main__':
    main()
