#!/usr/bin/env python3
"""Мост Anomaly ⇄ наша игра. Запусти: python3 tools/twin/server.py [путь/к/trace.jsonl]
Открой: http://localhost:8766/viewer.html

Туда-к-нам: отдаёт trace игры (GET /log). Без аргумента — живой, с аргументом — повтор.
От-нас-туда: творческий режим (POST /cmd) дописывает команды в файл, который читает
gamedata/scripts/varka_cmd.script. Ответ на команду приходит в trace (cmd_ok / cmd_fail).
"""
import http.server
import json
import os
import sys
import threading
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS = "/mnt/games/ANOMALY_DEV/appdata/logs"
LOG = sys.argv[1] if len(sys.argv) > 1 else os.path.join(LOGS, "varka_trace.jsonl")
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

    def log_message(self, fmt, *args):
        if "/log" not in str(args[0] if args else ""):  # опрос раз в полсекунды не спамит; args[0] бывает HTTPStatus
            super().log_message(fmt, *args)


os.chdir(HERE)
print(f"наша игра → http://localhost:{PORT}/viewer.html")
print(f"trace:   {LOG}")
print(f"команды: {CMD}")
try:
    http.server.ThreadingHTTPServer(("", PORT), Handler).serve_forever()
except KeyboardInterrupt:
    print("\nстоп")
