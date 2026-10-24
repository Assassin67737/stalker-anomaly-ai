#!/usr/bin/env bash
# Ночь 24.10.2026: два перебора в двойнике подряд (игра не нужна).
# Сосуд починен 24.10 вечером (VESSEL_AUDIT.md): старые результаты — out/sweep_*_1024_old_vessel. Оценка по куску на новом
# сосуде: ~3 ч на 11 потоках (быстрые fire_quick + night_quick: 20 800 боёв за 45 мин; старый сосуд — 5 ч 50 мин).
#   1. sweeps/fire_1024.lua  — тактика огня как доктрина (перекаты, подавление) + против ванили целиком, ~50 мин
#   2. sweeps/night_1024.lua — гранаты v2 × слух, 72 000 боёв (без лёжа), ~2 ч
#   tools/twin/sim/night_1024.sh                 запустить
#   POWEROFF=1 tools/twin/sim/night_1024.sh      и выключить компьютер после обоих отчётов
# Отчёты: sim/out/sweep_fire_1024/report.md, sim/out/sweep_night_1024/report.md.
# Ctrl+C на любом этапе — всё останавливается, компьютер НЕ выключается.
set -u
STOP=0
trap 'STOP=1' INT TERM
HERE="$(cd "$(dirname "$0")" && pwd)"
POWEROFF=0 "$HERE/sweep.sh" sweeps/fire_1024.lua || STOP=1    # выключение — только в конце этого скрипта
[ "$STOP" = 1 ] && { echo "== прервано — не выключаю"; exit 130; }
POWEROFF=0 "$HERE/sweep.sh" sweeps/night_1024.lua || STOP=1
[ "$STOP" = 1 ] && { echo "== прервано — не выключаю"; exit 130; }
if [ "${POWEROFF:-0}" = 1 ]; then systemctl poweroff; fi
