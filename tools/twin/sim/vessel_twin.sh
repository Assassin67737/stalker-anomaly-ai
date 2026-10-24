#!/usr/bin/env bash
# Trace двойника для сверки сосуда (vessel.py): duel4 ×60 и m26 ×40, seed 1001+ → sim/out/. ~30 с на 12 потоках.
#   SET='wnd_hp=0.1 aim_q=0.25' sim/vessel_twin.sh     рычаги мира поверх сценариев
cd "$(dirname "$0")/.."
P=${P:-$(nproc)}
for s in $(seq 1001 1060); do echo "sim/scen/duel4.lua $s"; done > /tmp/vessel_jobs.$$
for s in $(seq 1001 1040); do echo "sim/scen/m26.lua $s"; done >> /tmp/vessel_jobs.$$
ARGS=""; for kv in ${SET:-}; do ARGS="$ARGS --set $kv"; done
export ARGS
xargs -P "$P" -L 1 sh -c 'luajit sim/run.lua "$0" --seed "$1" $ARGS >/dev/null' < /tmp/vessel_jobs.$$
rm -f /tmp/vessel_jobs.$$
python3 sim/vessel.py --game 'match/runs/night_ranks*.jsonl' --game 'match/runs/night_quads*.jsonl' \
  --game 'match/runs/night_squads*.jsonl' --game 'match/runs/ranks_here*.jsonl' \
  --twin 'sim/out/duel4_s1[0-9][0-9][0-9].jsonl' --twin 'sim/out/twin_m26_s1[0-9][0-9][0-9].jsonl'
