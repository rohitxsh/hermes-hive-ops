#!/usr/bin/python3
"""Local Hermes patch (2026-11-06): the MCP OAuth callback listener (`hermes mcp login`) served one connection at a
time. Browsers open a spare "preconnect" TCP connection to a page's host and send nothing on it; the listener
accepted that one and waited on it forever while the real `/callback?code=...` sat unread in the backlog, so the
login hung (it worked only when the browser happened not to preconnect). Serve each connection in its own daemon
thread instead (stdlib ThreadingHTTPServer). Idempotent; `--check` reports; `--test` reproduces the hang case with
Hermes's venv python. Re-run after `hermes update`."""
import shutil
import sys
from pathlib import Path

ROOT = Path.home() / ".hermes/hermes-agent"
F = ROOT / "tools/mcp_oauth.py"
MARK = "local patch (2026-11-06): threaded oauth callback"
OLD = '        server = HTTPServer(("127.0.0.1", port), handler_cls, bind_and_activate=False)\n'
NEW = (f'        # {MARK}: an idle browser preconnect must not block the real /callback\n'
       '        from http.server import ThreadingHTTPServer\n'
       '        server = ThreadingHTTPServer(("127.0.0.1", port), handler_cls, bind_and_activate=False)\n')


def selftest():
    import socket, threading, time, urllib.request
    from http.server import BaseHTTPRequestHandler
    sys.path.insert(0, str(ROOT))
    import tools.mcp_oauth as m

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    srv = m._start_callback_server(port, H)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()
    idle = socket.create_connection(("127.0.0.1", port))   # the browser's empty preconnect
    time.sleep(0.3)
    t0 = time.time()
    body = urllib.request.urlopen(f"http://127.0.0.1:{port}/callback?code=x&state=y", timeout=5).read()
    assert body == b"ok" and time.time() - t0 < 3, "callback blocked behind an idle connection"
    idle.close(); srv.shutdown(); srv.server_close()
    print("selftest ok: callback served while a preconnect is open")


t = F.read_text(encoding="utf-8")
if "--check" in sys.argv:
    print("ok" if MARK in t else "missing")
    sys.exit(0 if MARK in t else 1)
if "--test" in sys.argv:
    selftest()
    sys.exit(0)
if MARK not in t:
    assert t.count(OLD) == 1, "tools/mcp_oauth.py: anchor not found once; upstream changed, patch by hand"
    t = t.replace(OLD, NEW)
    compile(t, str(F), "exec")
    bak = Path(str(F) + ".bak-2026-11-06-oauththreads")
    if not bak.exists():
        shutil.copy2(F, bak)
    F.write_text(t, encoding="utf-8")
    print("patched", F)
print("ok")
