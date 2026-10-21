#!/usr/bin/env bash
# Ночной прогон (21.10.2026): N матчей → архив → закрыть игру → выключить компьютер.
#
#   tools/twin/match/night.sh [N] [спек]        по умолчанию 200 матчей, matches/l07_night.json
#   NO_POWEROFF=1 tools/twin/match/night.sh 2   проба: всё то же, но компьютер не выключать
#
# Перед запуском: игра на Армейских складах (сейв загружен), g_always_active on, в опциях игры
# выключены выброс и пси-шторм, запущен tools/twin/server.py, вкладку вьювера ЗАКРЫТЬ (за ночь
# trace вырастет до сотен МБ, вьювер перечитывает его целиком раз в полсекунды).
#
# Пока идёт серия, systemd-inhibit держит блокировку «простой/сон»: hypridle не гасит экран и не
# блокирует сессию (с погашенным экраном игра может встать). Предполётная проверка: если сервер или
# игра не отвечают — скрипт выходит сразу и компьютер НЕ выключает (заметишь, пока не лёг).
set -u
N=${1:-200}
SPEC=${2:-matches/l07_night.json}
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
echo "== серия: $N матчей ($SPEC), лог раннера: $ARCH/runner.log"
echo "   примерно $((N * 5 / 2 / 60)) ч (матч в среднем ~2.5 мин с уборкой)"
systemd-inhibit --what=idle:sleep:handle-lid-switch --who=varka --why="ночной прогон матчей" \
    python3 -u run.py "$SPEC" --n "$N" 2>&1 | tee "$ARCH/runner.log"

echo "== закрываю игру"
curl -s -X POST -H 'Content-Type: application/json' -d '{"cmd":"quit","args":[]}' "$SERVER/cmd" >/dev/null
for _ in $(seq 60); do
    pgrep -f AnomalyDX11.exe >/dev/null || break
    sleep 2
done

echo "== архив: $ARCH"
cp "$LOGS/varka_trace.jsonl" "$ARCH/" && gzip -f "$ARCH/varka_trace.jsonl"
cp "$LOGS"/xray_*.log "$ARCH/" 2>/dev/null
find "$LOGS" -maxdepth 1 -name '*.mdmp' -newer "$ARCH/runner.log.start" -exec cp {} "$ARCH/" \;   # ночной краш — дамп рядом
cp results.jsonl "$ARCH/results_snapshot.jsonl"
sync

if [ "${NO_POWEROFF:-0}" = 1 ]; then
    echo "== NO_POWEROFF=1 — компьютер не выключаю"
else
    echo "== выключаю компьютер через 60 с (Ctrl+C — отменить)"
    sleep 60
    systemctl poweroff
fi
