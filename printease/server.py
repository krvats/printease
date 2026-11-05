"""PrintEase — HTTP server and API dispatcher."""
from __future__ import annotations

import json
import os
import pathlib
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

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
    queues          as list_queues,
    package_commands,
    remove_queue,
    run_priv,
    set_defaults,
    setup_queue,
)

def get_papersize(queue):
    """Return the default papersize for a queue (best-effort)."""
    import subprocess
    try:
        out = subprocess.check_output(
            ["lpoptions", "-p", queue, "-l"], text=True, timeout=5, stderr=subprocess.DEVNULL
        )
        for line in out.splitlines():
            if line.lower().startswith("pagesize") or line.lower().startswith("media"):
                # find the *selected* value (marked with *)
                for token in line.split():
                    if token.startswith("*"):
                        return token.lstrip("*")
    except Exception:
        pass
    return "A4"

_HERE = pathlib.Path(__file__).parent
_UI   = _HERE / "ui" / "index.html"
_TOKEN = secrets.token_hex(32)
_HOST  = "127.0.0.1"
_PORT  = 8765


# ── helpers ─────────────────────────────────────────────────────────────────

def _json(obj, status=200):
    body = json.dumps(obj, default=str).encode()
    return status, body, "application/json"


def _ok(**kw):
    return _json({"ok": True, **kw})


def _err(msg, status=400):
    return _json({"ok": False, "error": msg}, status)


def _read_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    return json.loads(handler.rfile.read(length)) if length else {}


# ── request handler ──────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):  # silence default access log
        pass

    def _guard(self):
        """Return True if request passes security checks."""
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
        self.end_headers()
        self.wfile.write(body)

    def _dispatch(self, status, body, ctype):
        self._send(status, body, ctype)

    # ── GET ──────────────────────────────────────────────────────────────────

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        if path == "/":
            html = _UI.read_text(encoding="utf-8")
            html = html.replace("__TOKEN__",   _TOKEN)
            html = html.replace("__VERSION__", __version__)
            body = html.encode()
            self._send(200, body, "text/html; charset=utf-8")
            return

        if not self._guard():
            return

        qs = parse_qs(parsed.query)
        queue = qs.get("queue", [None])[0]

        routes = {
            "/api/printers":  self._api_printers,
            "/api/queues":    self._api_queues,
            "/api/jobs":      lambda: self._api_jobs(queue),
            "/api/options":   lambda: self._api_options(queue),
            "/api/ink":       lambda: self._api_ink(queue),
            "/api/papersize": lambda: self._api_papersize(queue),
            "/api/distro":    self._api_distro,
            "/api/version":   self._api_version,
        }

        handler = routes.get(path)
        if handler:
            self._dispatch(*handler())
        else:
            self._send(404, b"Not Found", "text/plain")

    # ── POST ─────────────────────────────────────────────────────────────────

    def do_POST(self):
        if not self._guard():
            return
        path = urlparse(self.path).path

        routes = {
            "/api/setup":        self._api_setup,
            "/api/print":        self._api_print,
            "/api/cancel":       self._api_cancel,
            "/api/set-defaults": self._api_set_defaults,
            "/api/remove-queue": self._api_remove_queue,
            "/api/install-pkg":  self._api_install_pkg,
        }

        handler = routes.get(path)
        if handler:
            self._dispatch(*handler())
        else:
            self._send(404, b"Not Found", "text/plain")

    # ── API implementations ──────────────────────────────────────────────────

    def _api_printers(self):
        try:
            return _json(detect_printers())
        except Exception as e:
            return _err(str(e))

    def _api_queues(self):
        try:
            return _json(list_queues())
        except Exception as e:
            return _err(str(e))

    def _api_jobs(self, queue):
        try:
            return _json(list_jobs(queue))
        except Exception as e:
            return _err(str(e))

    def _api_options(self, queue):
        if not queue:
            return _err("queue parameter required")
        try:
            return _json(get_options(queue))
        except Exception as e:
            return _err(str(e))

    def _api_ink(self, queue):
        try:
            return _json(get_ink_levels(queue) if queue else {})
        except Exception as e:
            return _err(str(e))

    def _api_papersize(self, queue):
        try:
            return _json({"papersize": get_papersize(queue) if queue else "a4"})
        except Exception as e:
            return _err(str(e))

    def _api_distro(self):
        try:
            d = distro()
            pkgs = package_commands({"packages": {}})
            return _json({"distro": d, "package_manager": pkgs.get("manager", "")})
        except Exception as e:
            return _err(str(e))

    def _api_version(self):
        return _json({"version": __version__})

    def _api_setup(self):
        try:
            data = _read_body(self)
            uri  = data.get("uri", "")
            name = data.get("name", "")
            if not uri or not name:
                return _err("uri and name required")

            drivers = list_drivers(uri)
            profile_name = data.get("profile", "generic")

            # load profile JSON
            profile_path = _HERE.parent / "profiles" / f"{profile_name}.json"
            if not profile_path.exists():
                profile_path = _HERE.parent / "profiles" / "generic.json"
            profile = json.loads(profile_path.read_text())

            driver = find_driver(profile, drivers)
            if not driver:
                driver = "everywhere"  # IPP Everywhere universal fallback

            ppd_opts = data.get("ppd_options", {})
            ok, msg = setup_queue(name, uri, driver, ppd_opts)
            if ok:
                return _ok(queue=name, driver=driver, message=msg)
            return _err(msg)
        except Exception as e:
            return _err(str(e))

    def _api_print(self):
        try:
            data  = _read_body(self)
            queue = data.get("queue", "")
            filepath = data.get("file", "")
            if not queue or not filepath:
                return _err("queue and file required")
            args = build_print_args(
                queue=queue,
                copies=int(data.get("copies", 1)),
                media=data.get("media", ""),
                sides=data.get("sides", ""),
                quality=data.get("quality", ""),
                color=data.get("color", ""),
                grayscale=bool(data.get("grayscale", False)),
                resolution=data.get("resolution", ""),
                scale=bool(data.get("fit_to_page", False)),
                extra=data.get("extra", {}),
            )
            import subprocess
            result = subprocess.run(["lp"] + args + [filepath],
                                    capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                job_id = ""
                for token in result.stdout.split():
                    if token.startswith("request"):
                        job_id = token
                return _ok(job_id=job_id)
            return _err(result.stderr.strip() or "lp failed")
        except Exception as e:
            return _err(str(e))

    def _api_cancel(self):
        try:
            data   = _read_body(self)
            job_id = data.get("job_id", "")
            if not job_id:
                return _err("job_id required")
            ok, msg = cancel_job(job_id)
            if ok:
                return _ok(message=msg)
            return _err(msg)
        except Exception as e:
            return _err(str(e))

    def _api_set_defaults(self):
        try:
            data    = _read_body(self)
            queue   = data.get("queue", "")
            options = data.get("options", {})
            if not queue or not options:
                return _err("queue and options required")
            ok, msg = set_defaults(queue, options)
            if ok:
                return _ok(message=msg)
            return _err(msg)
        except Exception as e:
            return _err(str(e))

    def _api_remove_queue(self):
        try:
            data  = _read_body(self)
            queue = data.get("queue", "")
            if not queue:
                return _err("queue required")
            ok, msg = remove_queue(queue)
            if ok:
                return _ok(message=msg)
            return _err(msg)
        except Exception as e:
            return _err(str(e))

    def _api_install_pkg(self):
        """Trigger package install for printer drivers (best-effort)."""
        try:
            data    = _read_body(self)
            profile = data.get("profile", {})
            cmds    = package_commands(profile)
            if not cmds.get("install"):
                return _ok(message="No packages to install for this profile.")
            import subprocess
            pkgs = " ".join(cmds.get("packages", []))
            # We just return the command; the UI shows it.
            return _ok(command=cmds.get("install", ""), packages=cmds.get("packages", []))
        except Exception as e:
            return _err(str(e))


# ── server entry point ───────────────────────────────────────────────────────

class _ReuseServer(ThreadingHTTPServer):
    allow_reuse_address = True   # SO_REUSEADDR — no "Address in use" after crash/restart


def main():
    port = int(os.environ.get("PRINTEASE_PORT", _PORT))
    host = os.environ.get("PRINTEASE_HOST", _HOST)
    url  = f"http://{host}:{port}/"

    try:
        httpd = _ReuseServer((host, port), _Handler)
    except OSError as exc:
        if exc.errno == 98:   # EADDRINUSE
            print(f"PrintEase already running on port {port}. Opening browser.")
            webbrowser.open(url)
            return
        raise
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    print(f"PrintEase {__version__} running → {url}")

    # Give the server a moment, then open the browser in a separate thread
    # so it never blocks the daemon process from running.
    def _open():
        time.sleep(0.4)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()

    try:
        t.join()          # block here — the launcher's nohup keeps us alive
    except KeyboardInterrupt:
        httpd.shutdown()
