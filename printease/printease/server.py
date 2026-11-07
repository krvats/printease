"""PrintEase local server + app-window launcher. Stdlib only, bound to 127.0.0.1."""
import json, os, re, secrets, shutil, sys, tempfile, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from . import __version__, core

TOKEN = secrets.token_urlsafe(16)
STATE = {"ping": time.time(), "seen": False}
UI = Path(__file__).parent / "ui" / "index.html"


def api(path, q, body, headers):
    P = core.load_profiles()
    prof = lambda i: P.get(i) or P["generic"]
    if path == "ping":
        STATE.update(ping=time.time(), seen=True); return {"ok": True}
    if path == "status":
        return {"cups": bool(shutil.which("lpstat")), "distro": core.distro(), "version": __version__,
                "printers": core.detect_printers(), "queues": core.queues()}
    if path == "setup":
        j = json.loads(body or b"{}")
        return core.setup_queue(j["uri"], prof(j.get("profile")))
    if path == "install-drivers":
        j = json.loads(body or b"{}")
        res = []
        for argv, root in core.package_commands(prof(j.get("profile"))):
            rc, out, err = (core.run_priv if root else core.run)(argv, timeout=900)
            res.append({"cmd": " ".join(argv[:3]), "ok": rc == 0, "message": (err or out).strip()[-300:]})
        return {"results": res or [{"cmd": "nothing to install", "ok": True, "message": ""}]}
    if path == "options":
        qn = q["queue"][0]; opts = core.queue_options(qn)
        return {"options": opts, "borderless": core.borderless_sizes(opts), "ink": core.ink_levels(qn)}
    if path == "print":
        name = re.sub(r"[^\w.\-]", "_", os.path.basename(headers.get("X-Filename", "file")))
        tmp = Path(tempfile.mkdtemp()) / (core.unquote_name(name))
        tmp.write_bytes(body)
        g = lambda k, d="": q.get(k, [d])[0]
        return core.print_file(g("queue"), tmp, size=g("size", "A4"), borderless=g("borderless") == "1",
                               photo=g("photo") == "1", copies=int(g("copies", "1") or 1))
    if path == "test":
        return core.print_generated(q["queue"][0], q.get("kind", ["edge"])[0], borderless=q.get("kind", ["edge"])[0] == "edge")
    if path == "probe":
        j = json.loads(body or b"{}")
        return {"report": core.probe_siblings(prof(j.get("profile")), j["uri"], create=j.get("create", False), main=j.get("queue"))}
    if path == "maintenance":
        p = prof(json.loads(body or b"{}").get("profile"))
        return {"steps": p.get("maintenance", []), "notes": p.get("notes", "")}
    if path == "sync":
        return core.sync_profiles()
    if path == "update":
        return core.self_update()
    if path == "star":
        webbrowser.open(f"https://github.com/{core.REPO}"); return {"ok": True, "message": "Thank you! The printer will not jam today."}
    if path == "contribute":
        d = core.learn_draft(json.loads(body or b"{}").get("printer", {}))
        webbrowser.open(core.issue_url(d)); return {"ok": True}
    return {"ok": False, "message": "unknown endpoint"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, data, ctype="application/json"):
        raw = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw))); self.send_header("Cache-Control", "no-store"); self.end_headers()
        self.wfile.write(raw)

    def _handle(self):
        host = self.headers.get("Host", "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            return self._send(403, {"error": "forbidden"})
        u = urlparse(self.path)
        if u.path == "/" and self.command == "GET":
            html = UI.read_text().replace("__TOKEN__", TOKEN).replace("__VERSION__", __version__)
            return self._send(200, html.encode(), "text/html; charset=utf-8")
        if not u.path.startswith("/api/") or self.headers.get("X-Token") != TOKEN:
            return self._send(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        try:
            self._send(200, api(u.path[5:], parse_qs(u.query), body, self.headers))
        except Exception as e:
            self._send(200, {"ok": False, "message": f"{type(e).__name__}: {e}"})

    do_GET = do_POST = _handle


def open_window(url):
    for b in ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome", "brave", "microsoft-edge"):
        exe = shutil.which(b)
        if exe:
            os.spawnv(os.P_NOWAIT, exe, [exe, f"--app={url}", "--window-size=1060,700"]); return
    if shutil.which("xdg-open"):
        os.spawnvp(os.P_NOWAIT, "xdg-open", ["xdg-open", url])
    else:
        webbrowser.open(url)


def watchdog(keep):
    start = time.time()
    while True:
        time.sleep(3)
        idle = time.time() - STATE["ping"]
        if not keep and ((STATE["seen"] and idle > 20) or (not STATE["seen"] and time.time() - start > 90)):
            os._exit(0)


def main():
    keep = "--keep-alive" in sys.argv
    srv = ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PRINTEASE_PORT", "0"))), H)
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"PrintEase running at {url}", flush=True)
    threading.Thread(target=watchdog, args=(keep,), daemon=True).start()
    if "--no-open" not in sys.argv:
        open_window(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
