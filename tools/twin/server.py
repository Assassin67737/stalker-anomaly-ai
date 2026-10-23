#!/usr/bin/env python3
"""Мост Anomaly ⇄ наша игра. Запусти: python3 tools/twin/server.py [путь/к/trace.jsonl]
Открой: http://localhost:8766/viewer.html

Двойник вместо игры (пульт генерала, 21.10):  python3 tools/twin/server.py --twin [sim/scen/kotel1.lua]
  → http://localhost:8766/viewer3d.html. Сервер сам запускает sim/live.lua; протокол команд тот же.

Туда-к-нам: отдаёт trace игры (GET /log). Без аргумента — живой, с аргументом — повтор.
От-нас-туда: творческий режим (POST /cmd) дописывает команды в файл, который читает
gamedata/scripts/varka_cmd.script. Ответ на команду приходит в trace (cmd_ok / cmd_fail).
"""
import atexit
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS = "/mnt/games/ANOMALY_DEV/appdata/logs"
TWIN = "--twin" in sys.argv
args = [a for a in sys.argv[1:] if a != "--twin"]
if TWIN:
    SCEN = os.path.abspath(args[0]) if args else os.path.join(HERE, "sim", "scen", "kotel1.lua")
    os.makedirs(os.path.join(HERE, "sim", "out"), exist_ok=True)
    # второй двойник на другом порту (тесты) пишет в свои файлы — не мешает идущему котлу
    tag = "" if os.environ.get("PORT", "8766") == "8766" else "_" + os.environ["PORT"]
    LOG = os.path.join(HERE, "sim", "out", f"live{tag}.jsonl")
    CMD = os.path.join(HERE, "sim", "out", f"live_cmd{tag}.txt")
else:
    LOG = args[0] if args else os.path.join(LOGS, "varka_trace.jsonl")
    CMD = os.path.join(LOGS, "varka_cmd.txt")
PORT = int(os.environ.get("PORT", 8766))

# Файл команд: первая строка — id сессии (игра по нему понимает, что счёт начался заново)
seq = 0
lock = threading.Lock()
with open(CMD, "w", encoding="utf-8") as f:
    f.write(f"#session\t{uuid.uuid4().hex[:8]}\n")


def add_command(cmd, args):
    global seq
    clean = [str(a).replace("\t", " ").replace("\n", " ") for a in args]
    with lock:
        seq += 1
        with open(CMD, "a", encoding="utf-8") as f:
            f.write("\t".join([str(seq), cmd] + clean) + "\n")
        return seq


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith("/log"):
            return super().do_GET()  # статика: viewer.html, levels/
        try:
            with open(LOG, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            self.send_response(204)  # игра ещё не стартовала
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path.startswith("/areas/"):
            return self.save_areas()
        if self.path != "/cmd":
            self.send_response(404)
            self.end_headers()
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            n = add_command(body["cmd"], body.get("args", []))
            out = json.dumps({"seq": n}).encode()
            self.send_response(200)
        except Exception as ex:
            out = json.dumps({"error": str(ex)}).encode()
            self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    # Разметка территорий (23.10, редактор quads.html / quads3d.html): POST /areas/<уровень> → levels/<уровень>_areas.json.
    # Прежняя версия — в levels/areas_backup/<уровень>_<время>.json (руками нарисованное терять нельзя).
    def save_areas(self):
        name = self.path[len("/areas/"):]
        try:
            if not re.fullmatch(r"[a-z0-9_]+", name):
                raise ValueError("плохое имя уровня")
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            json.loads(body)  # только целый JSON
            path = os.path.join(HERE, "levels", name + "_areas.json")
            if os.path.exists(path):
                bdir = os.path.join(HERE, "levels", "areas_backup")
                os.makedirs(bdir, exist_ok=True)
                shutil.copy2(path, os.path.join(bdir, f"{name}_{time.strftime('%Y%m%d_%H%M%S')}.json"))
            with open(path + ".tmp", "wb") as f:
                f.write(body)
            os.replace(path + ".tmp", path)
            out = json.dumps({"ok": True, "bytes": len(body)}).encode()
            self.send_response(200)
        except Exception as ex:
            out = json.dumps({"error": str(ex)}).encode()
            self.send_response(400)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, fmt, *args):
        if "/log" not in str(args[0] if args else ""):  # опрос раз в полсекунды не спамит; args[0] бывает HTTPStatus
            super().log_message(fmt, *args)


os.chdir(HERE)
if TWIN:
    live = subprocess.Popen(["luajit", os.path.join(HERE, "sim", "live.lua"), SCEN, LOG, CMD])
    atexit.register(live.terminate)
    print(f"двойник: {SCEN} → http://localhost:{PORT}/viewer3d.html")
print(f"наша игра → http://localhost:{PORT}/viewer.html")
print(f"trace:   {LOG}")
print(f"команды: {CMD}")
try:
    http.server.ThreadingHTTPServer(("", PORT), Handler).serve_forever()
except KeyboardInterrupt:
    print("\nстоп")
