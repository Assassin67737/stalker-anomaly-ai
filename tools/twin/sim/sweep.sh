#!/usr/bin/env bash
# Ночной перебор в двойнике (23.10.2026): куски sweep.lua на всех ядрах → отчёт → (по желанию) выключить компьютер.
#
#   tools/twin/sim/sweep.sh [спек] [потоков]       по умолчанию sweeps/grenades.lua, потоков = ядер − 1
#   POWEROFF=1 tools/twin/sim/sweep.sh             после отчёта выключить компьютер
#
# Игра не нужна. Перезапуск продолжает с места (готовые бои в out/sweep_<имя>/part_*.jsonl пропускаются).
# Отчёт: out/sweep_<имя>/report.md (sweep_report.py), прогресс — sweep_report.py --progress.
# Ctrl+C / kill: потоки гаснут, отчёт по готовому пишется, компьютер НЕ выключается, выход с кодом 130.
set -u
STOP=0
trap 'STOP=1' INT TERM    # bash дождётся systemd-inhibit и только потом продолжит — уже со STOP=1
HERE="$(cd "$(dirname "$0")" && pwd)"
SPEC=${1:-sweeps/grenades.lua}
P=${2:-$(( $(nproc) - 1 ))}
cd "$HERE"
NAME=$(luajit -e "print(dofile('$SPEC').name)")
OUT="$HERE/out/sweep_$NAME"
mkdir -p "$OUT"
luajit sweep.lua "$SPEC" --count | tee "$OUT/count.txt"
pkill mpvpaper 2>/dev/null && echo "== обои (mpvpaper) погашены"
echo "== $P потоков, лог: $OUT/sweep.log"
date > "$OUT/started.txt"
systemd-inhibit --what=idle:sleep:handle-lid-switch --who=varka --why="перебор в двойнике" \
  bash -c "for i in \$(seq 0 $((P - 1))); do nice -n 10 luajit sweep.lua '$SPEC' --part \$i --of $P 2>>'$OUT/sweep.log' & done; wait"
if [ "$STOP" = 1 ]; then echo "прервано $(date)" > "$OUT/finished.txt"; else date > "$OUT/finished.txt"; fi
python3 sweep_report.py "$SPEC" > "$OUT/report.md" 2>>"$OUT/sweep.log"
echo "== отчёт: $OUT/report.md"
if [ "$STOP" = 1 ]; then echo "== ПРЕРВАНО (Ctrl+C) — не выключаю; перезапуск продолжит с места"; exit 130; fi
if [ "${POWEROFF:-0}" = 1 ]; then systemctl poweroff; fi
