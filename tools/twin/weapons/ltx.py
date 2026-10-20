"""Чтение конфигов оружия Anomaly с наследованием секций ([wpn_x]:parent)."""
import glob
import re

CONFIGS = '/mnt/games/ANOMALY_DEV/tools/_unpacked/configs'


def load_sections(pattern):
    secs = {}
    for f in glob.glob(f'{CONFIGS}/{pattern}', recursive=True):
        cur = None
        for line in open(f, encoding='latin-1'):
            line = line.split(';')[0].rstrip()
            m = re.match(r'^\[([^\]]+)\]\s*(?::\s*(.+))?', line)
            if m:
                cur = m.group(1)
                secs[cur] = {'_par': [p.strip() for p in (m.group(2) or '').split(',') if p.strip()]}
                continue
            if cur and '=' in line:
                k, v = line.split('=', 1)
                secs[cur][k.strip()] = v.strip()
    return secs


def get(secs, s, k, depth=0):
    if s not in secs or depth > 30:
        return None
    if k in secs[s]:
        return secs[s][k]
    for p in secs[s]['_par']:
        v = get(secs, p, k, depth + 1)
        if v is not None:
            return v
    return None
