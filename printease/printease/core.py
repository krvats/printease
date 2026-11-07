"""PrintEase core: CUPS detection, profiles, options, printing, sync. Stdlib only."""
import hashlib, json, os, re, shutil, struct, subprocess, tempfile, urllib.parse, urllib.request, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("PRINTEASE_HOME", Path.home() / ".local/share/printease"))
USER_PROFILES = DATA / "profiles"
REPO = os.environ.get("PRINTEASE_REPO", "YOUR_USER/printease")
BORDER_RE = re.compile(r"border|fullbleed|full|\.nm|\.fb", re.I)
REQUIRED = ("id", "name", "match")


def run(cmd, timeout=40, input=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"{cmd[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, "", "timed out"


def run_priv(cmd, **kw):
    """CUPS admin command: try plain (lpadmin group), then pkexec/sudo."""
    rc, out, err = run(cmd, **kw)
    if rc == 0 or os.environ.get("PRINTEASE_NO_PRIV") or os.geteuid() == 0:
        return rc, out, err
    gate = ["pkexec"] if shutil.which("pkexec") else ["sudo", "-n"]
    return run(gate + cmd, **kw)


# ---------- profiles ----------
def validate_profile(p):
    if not isinstance(p, dict) or any(k not in p for k in REQUIRED):
        return False
    if not re.fullmatch(r"[a-z0-9][a-z0-9\-]{0,60}", str(p["id"])):
        return False
    try:
        for r in list(p["match"]) + list(p.get("driver_hints", [])):
            re.compile(r)
    except (re.error, TypeError):
        return False
    return True


def load_profiles():
    found = {}
    for d in (ROOT / "profiles", USER_PROFILES):
        for f in sorted(d.glob("*.json")) if d.is_dir() else []:
            if f.name == "index.json":
                continue
            try:
                p = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            if validate_profile(p):
                found[p["id"]] = p
    return found


def match_profile(text, profiles=None):
    profiles = profiles or load_profiles()
    for p in sorted(profiles.values(), key=lambda p: -p.get("priority", 0)):
        if p["id"] != "generic" and any(re.search(m, text, re.I) for m in p["match"]):
            return p
    return profiles.get("generic") or {"id": "generic", "name": "Generic CUPS printer", "match": [".*"]}


# ---------- detection ----------
def detect_printers():
    _, out, _ = run(["lpinfo", "-v"])
    found = []
    for line in out.splitlines():
        _, _, uri = line.partition(" ")
        uri = uri.strip()
        if uri.startswith("usb://"):
            vendor, _, model = urllib.parse.unquote(uri[6:].split("?")[0]).partition("/")
            found.append({"uri": uri, "vendor": vendor, "model": model, "transport": "usb"})
        elif uri.startswith("dnssd://"):
            found.append({"uri": uri, "vendor": "", "model": urllib.parse.unquote(uri[8:].split("._")[0]),
                          "transport": "network"})
    profiles = load_profiles()
    for f in found:
        f["profile"] = match_profile(f"{f['vendor']} {f['model']}", profiles)["id"]
    return found


def queues():
    _, out, _ = run(["lpstat", "-p"])
    names = re.findall(r"^printer (\S+)", out, re.M)
    uris = dict(re.findall(r"device for (\S+): (\S+)", run(["lpstat", "-v"])[1]))
    m = re.search(r"destination: (\S+)", run(["lpstat", "-d"])[1])
    return [{"name": n, "uri": uris.get(n, ""), "default": bool(m and m.group(1) == n)} for n in names]


def list_drivers():
    _, out, _ = run(["lpinfo", "-m"], timeout=90)
    return [tuple(l.split(None, 1)) if " " in l else (l, "") for l in out.splitlines() if l.strip()]


def find_driver(profile, drivers=None):
    drivers = drivers if drivers is not None else list_drivers()
    for hint in profile.get("driver_hints", []):
        for did, desc in drivers:
            if re.search(hint, f"{did} {desc}", re.I):
                return did
    return next((d for d, _ in drivers if d == "everywhere"), None)


def distro():
    try:
        txt = Path("/etc/os-release").read_text().lower()
    except OSError:
        txt = ""
    for key, mgr in (("arch", "pacman"), ("cachyos", "pacman"), ("manjaro", "pacman"), ("debian", "apt"),
                     ("ubuntu", "apt"), ("mint", "apt"), ("fedora", "dnf"), ("suse", "zypper")):
        if key in txt:
            return mgr
    return next((m for m in ("pacman", "apt", "dnf", "zypper") if shutil.which(m)), "unknown")


def package_commands(profile, mgr=None, helper=None):
    """[(argv, needs_root)] to install a profile's drivers."""
    mgr = mgr or distro()
    pk = profile.get("packages", {})
    base = {"pacman": ["pacman", "-S", "--needed", "--noconfirm"], "apt": ["apt-get", "install", "-y"],
            "dnf": ["dnf", "install", "-y"], "zypper": ["zypper", "--non-interactive", "install"]}.get(mgr)
    cmds = [(base + pk[mgr], True)] if base and pk.get(mgr) else []
    if mgr == "pacman" and pk.get("aur"):
        helper = helper or next((h for h in ("paru", "yay") if shutil.which(h)), None)
        if helper:
            cmds.append(([helper, "-S", "--needed", "--noconfirm"] + pk["aur"], False))
    return cmds


# ---------- queue setup ----------
def slug(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_") or "Printer"


def setup_queue(uri, profile, name=None, drivers=None):
    name = slug(name or profile.get("queue_name") or profile["name"])
    did = find_driver(profile, drivers)
    if not did:
        return {"ok": False, "error": "no_driver",
                "message": f"No driver for {profile['name']} installed yet. Click 'Install drivers' first."}
    rc, out, err = run_priv(["lpadmin", "-p", name, "-E", "-v", uri, "-m", did, "-o", "printer-is-shared=false"])
    if rc != 0:
        return {"ok": False, "error": "lpadmin", "message": (err or out).strip()}
    if not any(q["default"] for q in queues()):
        run_priv(["lpadmin", "-d", name])
    return {"ok": True, "queue": name, "driver": did}


# ---------- options / borderless ----------
def parse_options(text):
    res = []
    for line in text.splitlines():
        m = re.match(r"^([\w.\-]+)/([^:]*):\s*(.*)$", line)
        if m:
            ch = m.group(3).split()
            default = next((c[1:] for c in ch if c.startswith("*")), ch[0] if ch else "")
            res.append({"key": m.group(1), "label": m.group(2).strip(), "choices": [c.lstrip("*") for c in ch],
                        "default": default})
    return res


def queue_options(queue):
    return parse_options(run(["lpoptions", "-p", queue, "-l"])[1])


def choices(opts, key):
    return next((o["choices"] for o in opts if o["key"].lower() == key.lower()), [])


def find_borderless(opts, size):
    return next((c for c in choices(opts, "PageSize") if BORDER_RE.search(c) and c.lower().startswith(size.lower())), None)


def borderless_sizes(opts):
    return [c for c in choices(opts, "PageSize") if BORDER_RE.search(c)]


def build_print_args(queue, path, opts, size="A4", borderless=False, photo=False, copies=1):
    args, notes = ["lp", "-d", queue, "-n", str(max(1, int(copies)))], []
    if borderless:
        bl = find_borderless(opts, size)
        args += ["-o", f"PageSize={bl or size}", "-o", "fit-to-page"]
        notes.append(f"Borderless size: {bl}." if bl else f"No borderless {size} in this driver; printing normally.")
    else:
        args += ["-o", f"PageSize={size}"]
    if photo:
        mts = choices(opts, "MediaType")
        mt = next((c for r in ("glossy", "photo") for c in mts if re.search(r, c, re.I)), None)
        if mt:
            args += ["-o", f"MediaType={mt}"]
        args += ["-o", "print-quality=5"]
    return args + [str(path)], notes


def print_file(queue, path, **kw):
    args, notes = build_print_args(queue, path, queue_options(queue), **kw)
    rc, out, err = run(args)
    return {"ok": rc == 0, "message": (out or err).strip(), "notes": notes}


def probe_siblings(profile, uri, create=False, main=None, models=None):
    """Check sibling-model PPDs for borderless sizes; optionally add extra queues."""
    models = models if models is not None else list_drivers()
    main = main or slug(profile.get("queue_name") or profile["name"])
    report = []
    for sib in profile.get("siblings", []):
        rx = re.compile(rf"epson.*[^A-Za-z0-9]{re.escape(sib)}([^0-9]|$)|[ /-]{re.escape(sib)}[ _.-]", re.I)
        hit = next((d for d, desc in models if rx.search(f"{d} {desc}")), None)
        if not hit:
            report.append({"model": sib, "status": "no driver installed"}); continue
        if run_priv(["lpadmin", "-p", "_probe", "-v", "socket://127.0.0.1:9", "-m", hit])[0] != 0:
            report.append({"model": sib, "status": "could not read"}); continue
        bl = borderless_sizes(queue_options("_probe"))
        run_priv(["lpadmin", "-x", "_probe"])
        item = {"model": sib, "driver": hit, "borderless": bl, "status": "borderless" if bl else "none"}
        if bl and create and sib.lower() != main.lower():
            q = f"{main}-{sib}"
            ok = run_priv(["lpadmin", "-p", q, "-E", "-v", uri, "-m", hit, "-o", "printer-is-shared=false"])[0] == 0
            item["queue"] = q if ok else None
        report.append(item)
    return report


# ---------- maintenance ----------
def ink_levels(queue):
    out = run(["lpoptions", "-p", queue])[1]
    def g(k):
        m = re.search(rf"{k}=(?:'([^']*)'|\"([^\"]*)\"|(\S+))", out)
        return [x for x in ((m.group(1) or m.group(2) or m.group(3) or "") if m else "").split(",") if x]
    names, levels, colors = g("marker-names"), g("marker-levels"), g("marker-colors")
    return [{"name": n, "level": int(l) if l.lstrip("-").isdigit() else -1,
             "color": colors[i] if i < len(colors) else ""} for i, (n, l) in enumerate(zip(names, levels))]


def _png(w, h, pixel):
    raw = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(w)) for y in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def make_test_png(path, kind="edge", w=620, h=877):
    """Stdlib PNG. 'edge' = gradient+frame to judge borderless; 'nozzle' = colour bars."""
    if kind == "nozzle":
        bars = [(0, 255, 255), (255, 0, 255), (255, 255, 0), (0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)]
        px = lambda x, y: bars[(y * len(bars)) // h] if (x // 6) % 2 == 0 else (255, 255, 255)
    else:
        def px(x, y):
            if x < 3 or y < 3 or x >= w - 3 or y >= h - 3:
                return (255, 255, 255)
            if abs(x - w // 2) < 2 or abs(y - h // 2) < 2:
                return (255, 255, 0)
            return (int(255 * (1 - y / h)), 40, int(255 * y / h))
    Path(path).write_bytes(_png(w, h, px))
    return str(path)


def print_generated(queue, kind, borderless=False):
    tmp = Path(tempfile.mkdtemp()) / f"printease-{kind}.png"
    make_test_png(tmp, kind)
    return print_file(queue, tmp, size="A4", borderless=borderless, photo=(kind == "edge"))


# ---------- updates / learning ----------
def fetch(url, timeout=12):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "printease"}), timeout=timeout) as r:
        return r.read()


def sync_profiles(fetcher=fetch, repo=None):
    base = f"https://raw.githubusercontent.com/{repo or REPO}/main/profiles/"
    try:
        index = json.loads(fetcher(base + "index.json"))
    except Exception as e:
        return {"ok": False, "message": f"Could not reach GitHub: {e}", "updated": []}
    USER_PROFILES.mkdir(parents=True, exist_ok=True)
    updated = []
    for item in index.get("profiles", []):
        fname = os.path.basename(item.get("file", ""))
        if not fname.endswith(".json") or fname == "index.json":
            continue
        target = USER_PROFILES / fname
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == item.get("sha256"):
            continue
        try:
            blob = fetcher(base + fname)
            if hashlib.sha256(blob).hexdigest() != item.get("sha256") or not validate_profile(json.loads(blob)):
                continue
        except Exception:
            continue
        target.write_bytes(blob)
        updated.append(fname)
    return {"ok": True, "updated": updated, "message": f"{len(updated)} profile(s) updated."}


def self_update():
    if not (ROOT / ".git").exists() or not shutil.which("git"):
        return {"ok": False, "message": "Not a git install. Re-run the one-line installer to update."}
    rc, out, err = run(["git", "-C", str(ROOT), "pull", "--ff-only"], timeout=90)
    return {"ok": rc == 0, "message": (out or err).strip()}


def learn_draft(printer, borderless=None):
    model = printer.get("model", "Unknown")
    pid = re.sub(r"[^a-z0-9]+", "-", f"{printer.get('vendor','')}-{model}".lower()).strip("-") or "new-printer"
    tok = re.escape(model.split()[0]) if model else "."
    return {"id": pid, "name": f"{printer.get('vendor','')} {model}".strip(), "match": [tok],
            "driver_hints": [tok], "borderless_sizes": borderless or [], "packages": {}, "maintenance": []}


def issue_url(draft, repo=None):
    q = urllib.parse.urlencode({"template": "printer-profile.yml", "title": f"Profile: {draft['name']}",
                                "profile": json.dumps(draft, indent=2)})
    return f"https://github.com/{repo or REPO}/issues/new?{q}"


def unquote_name(n):
    return n if n.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".txt", ".ps")) else n + ".pdf"
