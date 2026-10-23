#!/usr/bin/env python3
"""trace боя + события веры со стенда → один trace (по времени); опционально обрезать по t0+сек."""
import json, sys
src, bel, out = sys.argv[1], sys.argv[2], sys.argv[3]
cut = float(sys.argv[4]) if len(sys.argv) > 4 else None
rows = []
for f in (src, bel):
    for l in open(f):
        try: r = json.loads(l)
        except Exception: continue
        if isinstance(r, dict) and 't' in r: rows.append(r)
rows.sort(key=lambda r: r['t'])
t_seed = next(r['t'] for r in rows if r.get('ev') == 'bel_seed')
with open(out, 'w') as f:
    for r in rows:
        if cut is not None and r['t'] > t_seed + cut * 1000: break
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
