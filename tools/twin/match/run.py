#!/usr/bin/env python3
"""
Раннер матчей (20.10.2026): матч из JSON → живая Anomaly → кусок trace + оценка.

Нужно: запущен tools/twin/server.py (он пишет команды игре), игра на уровне матча.
Раннер говорит с игрой тем же протоколом, что творческий режим: POST /cmd → varka_cmd.script,
ответы (cmd_ok / cmd_fail / match_end) читает прямо из файла trace.

Формат матча (matches/*.json):
  {
    "id": "l07_square",                  имя матча
    "level": "l07_military",             уровень (запечённый в levels/)
    "limit_s": 300,                      лимит времени
    "zone": {"x": 40, "z": 10, "r": 15}, точка-задача: держит тот, у кого в радиусе только свои
    "spectator": {"x": 30, "z": 40},     куда поставить игрока смотреть (рядом — иначе отряды уйдут в офлайн)
    "ghost": true,                       отряды нейтральны к игроку
    "speed": 1,                          time_factor на время матча
    "hour": 10,                          перед серией перевести часы игры до этого часа (бои при свете)
    "sides": {
      "A": {"director": "shturm",        пресет | "off" (ваниль) | "default" | "random"
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
    "matchup": "random" — фракции и ранги сторон выбираются по правилам пар (pick_matchup): только
                          ВРАГИ по отношениям группировок (≤ -1000 в обе стороны; игра отвечает на
                          команду rel, без игры — базовая матрица game_relations.ltx); ИИГ против
                          всех, кроме Монолита и Греха, — на ступень ниже по рангу
  Вся локация (смарт-террейны — места, куда ходит симуляция; список игра выгружает сама, кэш levels/<уровень>_smarts.json):
    "zone": {"smart": "random", "r": 15}       точка матча — случайный смарт (или имя, или список имён)
    "at": {"smart_ring": [50, 120]}            спавн — смарт на таком расстоянии от точки; у B — с другой стороны
    "spectator": "zone"                         игрок встаёт на точку (с g_god on — безопасно)
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
import json
import math
import os
import random
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


def place(spec, setup, smarts, rng, lvl=None):
    """Точка матча и места спавна, если они заданы через смарты. Меняет setup на месте."""
    zone = dict(spec['zone'])
    if 'smart' in zone:
        names = [s['name'] for s in smarts]
        want = zone['smart']
        pick_from = names if want == 'random' else (want if isinstance(want, list) else [want])
        pick_name = rng.choice(pick_from)
        sm = next(s for s in smarts if s['name'] == pick_name)
        zone.update(x=sm['x'], z=sm['z'], name=sm['name'])
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
                    if lvl.has_node(x, z):
                        q['at'] = {'x': x, 'z': z, 'smart': None}
                        break
                else:
                    raise RuntimeError(f"нет места для спавна стороны {side} в {ring} м от точки")
            else:
                raise RuntimeError(f"нет смартов в {ring} м от точки {zone.get('name', '')} для стороны {side}")
            if side == 'A':
                ang_a = a
    return zone


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


def setup_of(spec, rng):
    """Конкретный матч из спека с разбросом: кто, сколько, какого ранга, откуда."""
    out = {}
    for s in ('A', 'B'):
        side = spec['sides'][s]
        out[s] = {
            'director': pick(side.get('director', 'default'), rng, RANDOM_DIRECTORS),
            'start': side.get('start', 'advance'),
            'squads': [{
                'faction': pick(q['faction'], rng),
                'tier': pick(q.get('tier', 'advanced'), rng, TIERS),
                'n': rng.randint(*q['n']) if isinstance(q.get('n'), list) else q.get('n', 4),
                'at': pick(q['at'], rng),
            } for q in side['squads']],
        }
    if spec.get('matchup') == 'random':  # фракции и ранги — по правилам пар, поверх того, что в спеке
        (fa, ta), (fb, tb) = pick_matchup(rng)
        for q in out['A']['squads']:
            q['faction'], q['tier'] = fa, ta
        for q in out['B']['squads']:
            q['faction'], q['tier'] = fb, tb
    if spec.get('swap') and rng.random() < 0.5:  # стороны меняются местами спавна
        a, b = out['A']['squads'], out['B']['squads']
        for qa, qb in zip(a, b):
            qa['at'], qb['at'] = qb['at'], qa['at']
    return out


# ---------- уровень: (x, z) → нода по запечённой картинке vid ----------

class Level:
    def __init__(self, name):
        self.meta = json.load(open(os.path.join(TWIN, 'levels', name + '.json')))
        self.vid = Image.open(os.path.join(TWIN, 'levels', name + '_vid.png')).convert('RGB').load()
        self.info = Image.open(os.path.join(TWIN, 'levels', name + '.png')).convert('RGBA').load()

    def y(self, x, z):
        """Высота верхней ноды в клетке (R подложки = высота в рамке уровня)."""
        m = self.meta
        i = min(max(round((x - m['box'][0]) / m['cell']), 0), m['w'] - 1)
        j = min(max(m['h'] - 1 - round((z - m['box'][2]) / m['cell']), 0), m['h'] - 1)
        return m['box'][1] + self.info[i, j][0] / 255 * (m['box'][4] - m['box'][1])

    def node(self, x, z, search=6):
        m = self.meta
        i0 = round((x - m['box'][0]) / m['cell'])
        j0 = m['h'] - 1 - round((z - m['box'][2]) / m['cell'])
        for rad in range(search + 1):  # ближайшая клетка с нодой, кольцами
            for di in range(-rad, rad + 1):
                for dj in range(-rad, rad + 1):
                    if max(abs(di), abs(dj)) != rad:
                        continue
                    i, j = i0 + di, j0 + dj
                    if 0 <= i < m['w'] and 0 <= j < m['h']:
                        r, g, b = self.vid[i, j]
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
    setup = setup_of(spec, rng)
    smarts = load_smarts(game, lvl, spec['level']) if ('smart' in spec['zone'] or any(
        isinstance(q.get('at'), dict) and 'smart_ring' in q['at']
        for s in ('A', 'B') for q in spec['sides'][s]['squads'])) else []
    zone = place(spec, setup, smarts, rng, lvl)
    zone_vid = lvl.node(zone['x'], zone['z'])
    sides, directors = {}, {}

    print(f"матч {spec['id']} #{tag}" + (f"  точка: {zone['name']}" if zone.get('name') else ''))
    sp = spec.get('spectator')
    if sp == 'zone':
        game.call('tp', zone_vid)
    elif sp:
        game.call('tp', lvl.node(sp['x'], sp['z']))
    cam = spec.get('camera', {'up': 18, 'back': 25})
    if cam:  # деморекорд: камера к точке матча (без деморекорда команда ничего не делает)
        zy = lvl.y(zone['x'], zone['z'])
        game.call('cam', round(zone['x'], 2), round(zy + cam.get('up', 18), 2), round(zone['z'] - cam.get('back', 25), 2),
                  round(zone['x'], 2), round(zy + 1, 2), round(zone['z'], 2))
    if sp and not game.dry:
        time.sleep(3)  # после переноса окрестность выходит в онлайн не сразу — иначе чистка её не видит
    if spec.get('speed'):
        game.call('time', spec['speed'])
    if 'clear' in CLEANUP:
        print('  площадка: ' + game.call('clear', zone_vid, spec.get('clear_r', 150)))

    born = None if game.dry else game.mark()  # отсюда ждём выхода отрядов в онлайн
    for s in ('A', 'B'):
        directors[s] = setup[s]['director']
        sides[s] = []
        for q in setup[s]['squads']:
            section = f"{SQUAD_PREFIX.get(q['faction'], q['faction'])}_sim_squad_{q.get('tier', 'advanced')}"
            vid = lvl.node(q['at']['x'], q['at']['z'])
            info = game.call('spawn', section, vid, q.get('n', 4), 1 if spec.get('ghost', True) else 0)
            sides[s].append(int(info.split(':')[1]))
    every = sides['A'] + sides['B']
    desc = lambda s: ' + '.join(f"{q['faction']} {q['tier']} ×{q['n']}" for q in setup[s]['squads'])
    print(f"  A {directors['A']} [{desc('A')}] {sides['A']}   B {directors['B']} [{desc('B')}] {sides['B']}")

    # все отряды должны выйти в онлайн, иначе стравить не получится
    if not game.dry:
        seen = set()

        def online(e):
            if e.get('ev') == 'npc_pos' and e.get('sq') in every:
                seen.add(e['sq'])
            return len(seen) == len(every)
        game.wait(online, 20, 'отряды не вышли в онлайн — поставь spectator ближе', born)

    for s in ('A', 'B'):
        for sq in sides[s]:
            game.call('preset', f'sq:{sq}', directors[s])
    for a in sides['A']:
        for b in sides['B']:
            game.call('hostile', f'sq:{a}', f'sq:{b}')
    for s in ('A', 'B'):
        if setup[s]['start'] == 'advance':
            for sq in sides[s]:
                game.call('order', f'sq:{sq}', 'move', zone_vid, 0)
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
    path = os.path.join(RUNS, f"{spec['id']}_{stamp}_{tag}.jsonl")
    with open(path, 'w', encoding='utf-8') as f:
        for e in game.buf:
            f.write(json.dumps(e, ensure_ascii=False) + '\n')
    game.buf = []

    r = scoring.score(scoring.load(path))
    r.update(directors=directors, setup=setup, zone=zone, run=os.path.relpath(path, HERE), spec=spec['id'])
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
    lvl = Level(spec['level'])
    rng = random.Random(args.seed)
    game = Game(args.dry)
    if spec.get('matchup') == 'random':
        src = load_relations(game)
        print(f'пары врагов ({src}): ' + ', '.join(f'{a}–{b}' for a, b in enemy_pairs()))
    if 'hour' in spec:  # серия при свете: часы игры вперёд до этого часа (один раз)
        print('часы игры: ' + game.call('hour', spec['hour']))
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
    if len(results) > 1:
        by = {}
        for r in results:
            by.setdefault(f"A {r['directors']['A']} vs B {r['directors']['B']}", []).append(r['score_a'])
        print('\nсерия:')
        for k, v in by.items():
            print(f'  {k}: матчей {len(v)}, средний счёт A {sum(v) / len(v):+.2f}')


if __name__ == '__main__':
    main()
