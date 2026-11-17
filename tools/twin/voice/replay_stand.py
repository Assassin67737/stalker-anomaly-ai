#!/usr/bin/env python3
"""
Сверка стенда голоса вне игры (17.11.2026): trace стенда (voice / voice_hear / npc_pos) → тот же varka_voice.script
в LuaJIT, луч — по level.cform (vision/librays.so). Показывает, что стенд должен был показать с починенным лучом.

  python3 voice/replay_stand.py [trace.jsonl] [уровень]
Нужны: корневой tools/twin/levels/src/<уровень>/{level.ai,level.cform}, appdata/varka_voice/<уровень>.bin.
"""
import collections, json, os, subprocess, sys, tempfile
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = '/home/ibra/Documents/My_Projects/AI_for_STALKER/tools/twin'
sys.path.insert(0, ROOT)
from level_ai import load  # noqa: E402

trace = sys.argv[1] if len(sys.argv) > 1 else '/mnt/games/ANOMALY_DEV/appdata/logs/varka_trace.jsonl'
lvl = sys.argv[2] if len(sys.argv) > 2 else 'l07_military'
_, nodes = load(os.path.join(ROOT, 'levels/src', lvl, 'level.ai'))
P = np.array([[n['x'], n['y'], n['z']] for n in nodes], dtype=np.float32)
vid = lambda x, y, z: int((((P[:, 0] - x) ** 2 + (P[:, 2] - z) ** 2) + 4 * (P[:, 1] - y) ** 2).argmin())  # noqa: E731
pos, ev = collections.defaultdict(list), []
for l in open(trace, encoding='utf-8', errors='replace'):
    try:
        e = json.loads(l)
    except ValueError:
        continue
    if e.get('ev') == 'npc_pos':
        pos[e['npc']].append((e['t'], e['px'], e['py'], e['pz'], e.get('comm', '?')))
    elif e.get('ev') in ('voice', 'voice_hear'):
        ev.append(e)
rows = []
for e in ev:
    if e['ev'] == 'voice':
        rows.append(['S', e['loud'], e['x'], e['y'], e['z'], vid(e['x'], e['y'], e['z'])])
    elif 'lx' in e:
        rows.append(['L', e['id'], e['lx'], e['ly'], e['lz'], vid(e['lx'], e['ly'], e['lz']), '?'])
    elif pos.get(e['id']):
        t, x, y, z, c = min(pos[e['id']], key=lambda p: abs(p[0] - e['t']))
        rows.append(['L', e['id'], x, y, z, vid(x, y, z), c])
with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
    json.dump(rows, f)
subprocess.run(['luajit', os.path.join(HERE, 'replay_stand.lua'), f.name, lvl], check=True)
