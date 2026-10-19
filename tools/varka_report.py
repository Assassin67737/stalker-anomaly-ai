#!/usr/bin/env python3
"""varka_report.py — сводка прогона полигона по трейсу VARKA-TC.

Запуск:  python3 varka/tools/varka_report.py [путь_к_varka_trace.jsonl]
По умолчанию читает живой лог игры. Трейс перезаписывается при каждом старте игры,
поэтому отчёт всегда про ПОСЛЕДНИЙ запуск.

Что печатает:
  1. Диагностическую цепочку (вера сеется → поиск → веер → HOLD) с вердиктом по шагу.
  2. Тревожные знаки: убийства веры, freeze, обрубленные поиски.
  3. Таблицу по отрядам.
"""
import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict

DEFAULT_LOG = "/mnt/games/ANOMALY_DEV/appdata/logs/varka_trace.jsonl"

TTY = sys.stdout.isatty()


def paint(text, code):
    return f"\033[{code}m{text}\033[0m" if TTY else text


def ok(text):
    return paint(text, "32")


def bad(text):
    return paint(text, "31")


def warn(text):
    return paint(text, "33")


def load(path):
    events, broken = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                broken += 1  # последняя строка может быть недописана, если игра ещё идёт
    return events, broken


def spans(events, start_ev, end_ev):
    """Длительности пар start→end на одного NPC, мс."""
    open_at, out = {}, []
    for e in events:
        if e["ev"] == start_ev:
            open_at[e["npc"]] = e["t"]
        elif e["ev"] == end_ev and e["npc"] in open_at:
            out.append(e["t"] - open_at.pop(e["npc"]))
    return out


def fmt_ms(values):
    if not values:
        return "—"
    return f"медиана {statistics.median(values) / 1000:.1f} с (n={len(values)})"


def step(n, title, passed, detail):
    mark = ok("✓") if passed else bad("✗")
    print(f"  {n}. {mark} {title:<28} {detail}")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_LOG
    if not os.path.exists(path):
        print(bad(f"нет трейса: {path}"))
        return 1

    events, broken = load(path)
    c = Counter(e["ev"] for e in events)
    age_min = (time.time() - os.path.getmtime(path)) / 60
    ts = [e["t"] for e in events if "t" in e]
    dur = (max(ts) - min(ts)) / 1000 if ts else 0

    print(f"\nVARKA report — {path}")
    print(f"  событий {len(events)}, игровое время {dur:.0f} с, файл обновлён {age_min:.0f} мин назад"
          + (warn(f", битых строк {broken}") if broken else ""))

    holds = [e for e in events if e["ev"] == "hold_enter"]
    modes = Counter(e.get("mode", "?") for e in holds)
    expires = [e for e in events if e["ev"] == "hold_expire"]
    fresh = sum(1 for e in expires if e.get("fresh"))

    print("\nЦепочка:")
    step(1, "вера сеется", c["belief_notice"] + c["belief_born"] > 0,
         f"notice {c['belief_notice']}, born {c['belief_born']}, "
         f"слух {c['alert_hear']}, труп {c['alert_corpse']}")
    step(2, "GOAP берёт поиск", c["search_start"] > 0,
         f"search_start {c['search_start']}, голос {c['bark']}")
    step(3, "веер сканируется", c["node_checked"] > 0,
         f"нод взято {c['search_node']}, проверено {c['node_checked']}")
    mode_txt = ", ".join(f"{m} {n}" for m, n in modes.most_common()) or "—"
    step(4, "HOLD читается", len(holds) > 0, f"hold_enter {len(holds)} ({mode_txt})")
    if expires:
        print(f"       истекло {len(expires)}: свежие вести → снова поиск {fresh}, "
              f"тишина → вера умерла {len(expires) - fresh}")

    print("\nТревожные знаки:")
    kills = Counter(e.get("reason", "?") for e in events if e["ev"] == "belief_kill")
    kill_txt = ", ".join(f"{r} {n}" for r, n in kills.items()) or "0"
    line = f"  belief_kill: {kill_txt}"
    print(bad(line) if kills.get("fan_swept") else line)
    print(f"  freeze: входов {c['freeze_enter']}, {fmt_ms(spans(events, 'freeze_enter', 'freeze_exit'))}")
    searches = spans(events, "search_start", "search_end")
    short = sum(1 for s in searches if s < 5000)
    line = f"  поиск длится: {fmt_ms(searches)}, короче 5 с: {short}"
    print(warn(line) if searches and short > len(searches) / 2 else line)
    if modes.get("here"):
        print(warn(f"  HOLD here {modes['here']}: глаза не нашли обзора — стоят где стоят"))
    if c["hold_enter"] and not modes.get("ow"):
        print(warn("  ни одного HOLD ow: глаза не сработали (проверь VARKA-EYES в xray-логе)"))

    comm = {}
    for e in events:
        if e["ev"] == "npc_pos":
            comm[e["sq"]] = e.get("comm", "?")
    per = defaultdict(Counter)
    npcs = defaultdict(set)
    for e in events:
        sq = e.get("sq")
        if not sq:
            continue
        if e["ev"] == "hold_enter":
            per[sq]["hold_" + e.get("mode", "?")] += 1
        per[sq][e["ev"]] += 1
        if e.get("npc"):
            npcs[sq].add(e["npc"])
    active = [sq for sq in per if per[sq]["search_start"] or per[sq]["freeze_enter"]]
    if active:
        print("\nОтряды, которые искали:")
        print(f"  {'отряд':>7} {'фракция':<10} {'бойцов':>6} {'поиск':>5} {'HOLD ow/cov/here':>16} "
              f"{'kill':>4} {'freeze':>6} {'голос':>5}")
        for sq in sorted(active, key=lambda s: -per[s]["search_start"]):
            p = per[sq]
            hold = f"{p['hold_ow']}/{p['hold_cover']}/{p['hold_here']}"
            print(f"  {sq:>7} {comm.get(sq, '?'):<10} {len(npcs[sq]):>6} {p['search_start']:>5} "
                  f"{hold:>16} {p['belief_kill']:>4} {p['freeze_enter']:>6} {p['bark']:>5}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
