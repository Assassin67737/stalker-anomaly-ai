#!/usr/bin/env bash
# Ночной прогон (21.10.2026): N матчей → архив → закрыть игру → выключить компьютер.
#
#   tools/twin/match/night.sh [N] [спек]        по умолчанию 200 матчей, matches/night_ranks.json
#   NO_POWEROFF=1 tools/twin/match/night.sh 2   проба: всё то же, но компьютер не выключать
#   CONDUCTOR=A tools/twin/match/night.sh 200 matches/night_quads.json
#                                               + дирижёр квадрантов (conductor.py) ведёт сторону A (или B, AB)
#
# Спеки night_ranks (бои по рангам 1–4 на 1–4) и night_squads (отряды 3–5) — "level": "here":
# идут на той локе, где стоит игра, на любой из запечённых (tools/twin/levels/index.json).
#
# Перед запуском: игра на нужной локе (сейв загружен), g_always_active on, в опциях игры
# выключены выброс и пси-шторм, запущен tools/twin/server.py, вкладку вьювера ЗАКРЫТЬ (за ночь
# trace вырастет до сотен МБ, вьювер перечитывает его целиком раз в полсекунды).
#
# Пока идёт серия, systemd-inhibit держит блокировку «простой/сон»: hypridle не гасит экран и не
# блокирует сессию (с погашенным экраном игра может встать). Предполётная проверка: если сервер или
# игра не отвечают — скрипт выходит сразу и компьютер НЕ выключает (заметишь, пока не лёг).
# Ctrl+C в любой момент (серия, 60 с до выключения): архив пишется, игра остаётся, компьютер НЕ выключается.
set -u
STOP=0
trap 'STOP=1' INT TERM
N=${1:-200}
SPEC=${2:-matches/night_ranks.json}
HERE="$(cd "$(dirname "$0")" && pwd)"
LOGS=/mnt/games/ANOMALY_DEV/appdata/logs
SERVER=${VARKA_SERVER:-http://localhost:8766}
cd "$HERE"

STAMP=$(date +%Y%m%d_%H%M)
ARCH="$HERE/runs_night_$STAMP"

echo "== предполётная проверка"
if ! python3 - <<'EOF'
import sys
sys.path.insert(0, '.')
import run
g = run.Game()
try:
    print('  игра отвечает: ' + g.call('rel', 'stalker', 'bandit', timeout=15)[:60])
except Exception as e:
    print(f'  НЕТ ОТВЕТА: {e}')
    sys.exit(1)
EOF
then
    echo "игра или сервер не отвечают — ничего не запускаю, компьютер не выключаю"
    exit 1
fi

mkdir -p "$ARCH"
touch "$ARCH/runner.log.start"   # метка времени: дампы новее неё — ночные
# живые обои (mpvpaper) жрут GPU всю ночь — гасим; при следующем входе в сессию стартуют сами
pkill mpvpaper 2>/dev/null && echo "== обои (mpvpaper) погашены"
COND_PID=""
if [ -n "${CONDUCTOR:-}" ]; then
    echo "== дирижёр квадрантов: сторона $CONDUCTOR, лог: $ARCH/conductor.log"
    python3 -u conductor.py --side "$CONDUCTOR" > "$ARCH/conductor.log" 2>&1 &
    COND_PID=$!
    trap '[ -n "$COND_PID" ] && kill "$COND_PID" 2>/dev/null' EXIT
fi
echo "== серия: $N матчей ($SPEC), лог раннера: $ARCH/runner.log"
echo "   примерно $((N * 5 / 2 / 60)) ч (матч в среднем ~2.5 мин с уборкой)"
systemd-inhibit --what=idle:sleep:handle-lid-switch --who=varka --why="ночной прогон матчей" \
    python3 -u run.py "$SPEC" --n "$N" 2>&1 | tee "$ARCH/runner.log"

[ -n "$COND_PID" ] && kill "$COND_PID" 2>/dev/null
if [ "$STOP" = 1 ]; then
    echo "== прервано (Ctrl+C) — игру не закрываю"
else
    echo "== закрываю игру"
    curl -s -X POST -H 'Content-Type: application/json' -d '{"cmd":"quit","args":[]}' "$SERVER/cmd" >/dev/null
    for _ in $(seq 60); do
        pgrep -f AnomalyDX11.exe >/dev/null || break
        sleep 2
    done
fi

echo "== архив: $ARCH"
cp "$LOGS/varka_trace.jsonl" "$ARCH/" && gzip -f "$ARCH/varka_trace.jsonl"
cp "$LOGS"/xray_*.log "$ARCH/" 2>/dev/null
find "$LOGS" -maxdepth 1 -name '*.mdmp' -newer "$ARCH/runner.log.start" -exec cp {} "$ARCH/" \;   # ночной краш — дамп рядом
cp results.jsonl "$ARCH/results_snapshot.jsonl"
sync

if [ "$STOP" = 1 ]; then
    echo "== прервано — компьютер не выключаю"
elif [ "${NO_POWEROFF:-0}" = 1 ]; then
    echo "== NO_POWEROFF=1 — компьютер не выключаю"
else
    echo "== выключаю компьютер через 60 с (Ctrl+C — отменить)"
    sleep 60
    if [ "$STOP" = 1 ]; then echo "== отменено"; else systemctl poweroff; fi
fi
