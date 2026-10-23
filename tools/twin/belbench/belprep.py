#!/usr/bin/env python3
"""trace боя → TSV для офлайн-стенда веры: npc_pos и смерти, по времени."""
import json, sys
src, out = sys.argv[1], sys.argv[2]
rows = []
for l in open(src):
    try: r = json.loads(l)
    except Exception: continue
    if not isinstance(r, dict) or 'ev' not in r: continue
    if r['ev'] == 'npc_pos':
        rows.append((r['t'], 'P', r['npc'], r['sq'], r['px'], r['py'], r['pz'], r.get('dx', 0), r.get('dz', 1),
                     r.get('be', -1), r.get('bsee', 0), r.get('cr', 0), r.get('wnd', 0), r.get('aid2', -1), r.get('comm', '?')))
    elif r['ev'] == 'death':
        rows.append((r['t'], 'D', r['npc']))
rows.sort(key=lambda x: x[0])
with open(out, 'w') as f:
    for r in rows: f.write('\t'.join(str(x) for x in r) + '\n')
print(len(rows), 'строк')
