"""PrintEase — HTTP server and API dispatcher (v2 fixed)."""
from __future__ import annotations

import json
import os
import pathlib
import secrets
import tempfile
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__
from .core import (
    build_print_args,
    cancel_job,
    detect_printers,
    distro,
    find_driver,
    ink_levels      as get_ink_levels,
    queue_options   as get_options,
    list_drivers,
    list_jobs,
    learn_draft,
    issue_url,
    queues          as list_queues,
    package_commands,
    make_test_png,
    print_file,
    probe_siblings,
    remove_queue,
    run_priv,
    self_update,
    set_defaults,
    setup_queue,
    slug,
    sync_profiles,
)

_HERE   = pathlib.Path(__file__).parent
_UI     = _HERE / "ui" / "index.html"
_TOKEN  = secrets.token_hex(32)
_HOST   = "127.0.0.1"
_PORT   = int(os.environ.get("PRINTEASE_PORT", 8765))

# Allowed upload extensions (never execute anything)
_UPLOAD_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".ps", ".txt", ".svg", ".pcl"}

# ── helpers ──────────────────────────────────────────────────────────────────

def _json(obj, status=200):
    body = json.dumps(obj, default=str).encode()
    return status, body, "application/json"

def _ok(**kw):
    return _json({"ok": True, **kw})

def _err(msg, status=400):
    return _json({"ok": False, "error": str(msg)}, status)

def _body_json(handler):
    n = int(handler.headers.get("Content-Length", 0))
    return json.loads(handler.rfile.read(n)) if n else {}

def _body_raw(handler):
    n = int(handler.headers.get("Content-Length", 0))
    return handler.rfile.read(n) if n else b""


# ── request handler ──────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass   # silence default access log

    def _guard(self):
        host = self.headers.get("Host", "").split(":")[0]
        if host not in ("127.0.0.1", "localhost", "[::1]"):
            self._send(403, b"Forbidden", "text/plain")
            return False
        token = self.headers.get("X-Token", "")
        if not secrets.compare_digest(token, _TOKEN):
            self._send(401, b"Unauthorized", "text/plain")
            return False
        return True

    def _send(self, status, body, ctype):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "null")
        self.end_headers()
        self.wfile.write(body)

    def _dispatch(self, status, body, ctype):
        self._send(status, body, ctype)

    # ── GET ──────────────────────────────────────────────────────────────────

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path   = parsed.path

        # Serve the UI (token + version injected)
        if path == "/":
            html = _UI.read_text(encoding="utf-8")
            html = html.replace("__TOKEN__",   _TOKEN)
            html = html.replace("__VERSION__", __version__)
            self._send(200, html.encode(), "text/html; charset=utf-8")
            return

        if not self._guard():
            return

        qs    = urllib.parse.parse_qs(parsed.query)
        queue = qs.get("queue", [None])[0]

        routes = {
            "/api/printers":  self._printers,
            "/api/queues":    self._queues,
            "/api/jobs":      lambda: self._jobs(queue),
            "/api/options":   lambda: self._options(queue),
            "/api/ink":       lambda: self._ink(queue),
            "/api/papersize": lambda: self._papersize(queue),
            "/api/distro":    self._distro,
            "/api/version":   self._version,
            "/api/ping":      lambda: _ok(pong=True),
        }

        handler = routes.get(path)
        if handler:
            self._dispatch(*handler())
        else:
            self._send(404, b"Not found", "text/plain")

    # ── POST ─────────────────────────────────────────────────────────────────

    def do_POST(self):
        if not self._guard():
            return
        path = urllib.parse.urlparse(self.path).path

        routes = {
            "/api/setup":        self._setup,
            "/api/print":        self._print,
            "/api/upload":       self._upload,
            "/api/cancel":       self._cancel,
            "/api/set-defaults": self._set_defaults,
            "/api/remove-queue": self._remove_queue,
            "/api/install-pkg":  self._install_pkg,
            "/api/test":         self._test,
            "/api/sync":         self._sync,
            "/api/update":       self._update,
            "/api/probe":        self._probe,
            "/api/contribute":   self._contribute,
        }

        handler = routes.get(path)
        if handler:
            self._dispatch(*handler())
        else:
            self._send(404, b"Not found", "text/plain")

    # ── API: GET endpoints ────────────────────────────────────────────────────

    def _printers(self):
        try:
            return _json(detect_printers())
        except Exception as e:
            return _err(e)

    def _queues(self):
        try:
            return _json(list_queues())
        except Exception as e:
            return _err(e)

    def _jobs(self, queue):
        try:
            return _json(list_jobs(queue))
        except Exception as e:
            return _err(e)

    def _options(self, queue):
        if not queue:
            return _err("queue parameter required")
        try:
            return _json(get_options(queue))
        except Exception as e:
            return _err(e)

    def _ink(self, queue):
        try:
            return _json(get_ink_levels(queue) if queue else [])
        except Exception as e:
            return _err(e)

    def _papersize(self, queue):
        try:
            if not queue:
                return _json({"papersize": "A4"})
            opts = get_options(queue)
            ps   = next((o for o in opts if o["key"].lower() == "pagesize"), None)
            default = ps["default"] if ps else "A4"
            return _json({"papersize": default})
        except Exception as e:
            return _err(e)

    def _distro(self):
        try:
            d  = distro()
            pc = package_commands({"packages": {}})
            return _json({"distro": d, "package_manager": pc[0][0][0] if pc else d})
        except Exception as e:
            return _err(e)

    def _version(self):
        return _json({"version": __version__})

    # ── API: POST endpoints ───────────────────────────────────────────────────

    def _upload(self):
        """Accept raw file bytes, save to /tmp, return filesystem path."""
        try:
            raw = _body_raw(self)
            if not raw:
                return _err("No file data received")
            if len(raw) > 150 * 1024 * 1024:   # 150 MB limit
                return _err("File too large (150 MB max)")

            fname  = urllib.parse.unquote(self.headers.get("X-Filename", "print_job"))
            suffix = pathlib.Path(fname).suffix.lower()
            if suffix not in _UPLOAD_EXTS:
                suffix = ".pdf"

            tmp = tempfile.NamedTemporaryFile(
                prefix="pe_", suffix=suffix, dir="/tmp", delete=False
            )
            tmp.write(raw)
            tmp.close()
            return _ok(path=tmp.name, filename=fname, size=len(raw))
        except Exception as e:
            return _err(e)

    def _setup(self):
        try:
            data = _body_json(self)
            uri  = data.get("uri", "")
            name = data.get("name", "")
            if not uri:
                return _err("uri required")

            # Load profile
            pid   = data.get("profile", "generic")
            pfile = _HERE.parent / "profiles" / f"{pid}.json"
            if not pfile.exists():
                pfile = _HERE.parent / "profiles" / "generic.json"
            profile = json.loads(pfile.read_text())

            drivers    = list_drivers()
            ppd_opts   = data.get("ppd_options", {})
            result     = setup_queue(uri, profile, name=name or None, drivers=drivers)
            if not result["ok"]:
                return _err(result.get("message", result.get("error", "Setup failed")))
            return _ok(queue=result["queue"], driver=result["driver"])
        except Exception as e:
            return _err(e)

    def _print(self):
        try:
            data     = _body_json(self)
            queue    = data.get("queue", "")
            filepath = data.get("file", "")

            if not queue or not filepath:
                return _err("queue and file are both required")
            if not pathlib.Path(filepath).exists():
                return _err(f"File not found on server: {filepath}")

            opts = get_options(queue)
            cmd, notes = build_print_args(
                queue      = queue,
                path       = filepath,
                opts       = opts,
                size       = data.get("media", "A4"),
                borderless = bool(data.get("borderless", False)),
                photo      = bool(data.get("photo", False)),
                copies     = int(data.get("copies", 1)),
                grayscale  = bool(data.get("grayscale", False)),
                resolution = data.get("resolution") or None,
                scale      = bool(data.get("fit_to_page", False)),
            )
            from .core import run
            rc, out, err = run(cmd, timeout=15)
            if rc == 0:
                job_id = next((t for t in out.split() if t.startswith("request")), "")
                return _ok(job_id=job_id, notes=notes)
            return _err((err or out).strip() or "lp returned non-zero")
        except Exception as e:
            return _err(e)

    def _cancel(self):
        try:
            data   = _body_json(self)
            job_id = data.get("job_id", "")
            if not job_id:
                return _err("job_id required")
            result = cancel_job(job_id)
            return _ok(**result) if result["ok"] else _err(result["message"])
        except Exception as e:
            return _err(e)

    def _set_defaults(self):
        try:
            data    = _body_json(self)
            queue   = data.get("queue", "")
            options = data.get("options", {})
            if not queue or not options:
                return _err("queue and options required")
            result = set_defaults(queue, options)
            return _ok(**result) if result["ok"] else _err(result["message"])
        except Exception as e:
            return _err(e)

    def _remove_queue(self):
        try:
            data  = _body_json(self)
            queue = data.get("queue", "")
            if not queue:
                return _err("queue required")
            result = remove_queue(queue)
            return _ok(**result) if result["ok"] else _err(result["message"])
        except Exception as e:
            return _err(e)

    def _install_pkg(self):
        """Return the install command (don't run it — UI shows it to user)."""
        try:
            data    = _body_json(self)
            profile = data.get("profile", {})
            mgr     = distro()
            cmds    = package_commands(profile, mgr=mgr)
            if not cmds:
                return _ok(commands=[], message="No packages needed for this profile.")
            return _ok(
                commands=[{"cmd": c[0], "needs_root": c[1]} for c in cmds],
                manager=mgr,
            )
        except Exception as e:
            return _err(e)

    def _test(self):
        """Generate and print a test page (edge or nozzle)."""
        try:
            data  = _body_json(self)
            queue = data.get("queue", "")
            kind  = data.get("kind", "edge")
            bl    = bool(data.get("borderless", False))
            if not queue:
                return _err("queue required")
            from .core import print_generated
            result = print_generated(queue, kind, borderless=bl)
            return _ok(**result) if result["ok"] else _err(result["message"])
        except Exception as e:
            return _err(e)

    def _sync(self):
        try:
            result = sync_profiles()
            return _ok(**result) if result["ok"] else _err(result["message"])
        except Exception as e:
            return _err(e)

    def _update(self):
        try:
            result = self_update()
            return _ok(**result) if result["ok"] else _err(result["message"])
        except Exception as e:
            return _err(e)

    def _probe(self):
        try:
            data = _body_json(self)
            queue = data.get("queue", "")
            uri   = data.get("uri", "")
            pid   = data.get("profile", "generic")
            create = bool(data.get("create", False))

            pfile = _HERE.parent / "profiles" / f"{pid}.json"
            if not pfile.exists():
                pfile = _HERE.parent / "profiles" / "generic.json"
            profile = json.loads(pfile.read_text())

            report = probe_siblings(profile, uri, create=create, main=slug(queue) if queue else None)
            return _ok(report=report)
        except Exception as e:
            return _err(e)

    def _contribute(self):
        try:
            data    = _body_json(self)
            printer = data.get("printer", {})
            draft   = learn_draft(printer)
            url     = issue_url(draft)
            webbrowser.open(url)
            return _ok(url=url, draft=draft)
        except Exception as e:
            return _err(e)


# ── server entry point ───────────────────────────────────────────────────────

class _Server(ThreadingHTTPServer):
    allow_reuse_address = True


def main():
    url = f"http://{_HOST}:{_PORT}/"
    try:
        httpd = _Server((_HOST, _PORT), _Handler)
    except OSError as exc:
        if exc.errno == 98:
            print(f"PrintEase already running. Opening {url}")
            webbrowser.open(url)
            return
        raise

    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    print(f"PrintEase {__version__}  →  {url}")
    print("Stop with Ctrl+C  |  Logs: none (quiet mode)")

    def _open():
        time.sleep(0.35)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()

    try:
        t.join()
    except KeyboardInterrupt:
        httpd.shutdown()
        print("\nStopped.")
