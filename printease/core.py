"""PrintEase core — CUPS detection, profiles, options, printing, job queue. Stdlib only."""
import hashlib, json, os, re, shutil, struct, subprocess, tempfile, urllib.parse, urllib.request, zlib
from pathlib import Path

ROOT         = Path(__file__).resolve().parent.parent
DATA         = Path(os.environ.get("PRINTEASE_HOME", Path.home() / ".local/share/printease"))
USER_PROFILES = DATA / "profiles"
REPO         = os.environ.get("PRINTEASE_REPO", "krvats/printease")
BORDER_RE    = re.compile(r"border|fullbleed|full|\.nm|\.fb", re.I)
REQUIRED     = ("id", "name", "match")


# ── subprocess helpers ──────────────────────────────────────────────────────

def run(cmd, timeout=40, input=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"{cmd[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, "", "timed out"


def run_priv(cmd, **kw):
    """Try plain (lpadmin group), then pkexec, then sudo -n."""
    rc, out, err = run(cmd, **kw)
    if rc == 0 or os.environ.get("PRINTEASE_NO_PRIV") or os.geteuid() == 0:
        return rc, out, err
    gate = ["pkexec"] if shutil.which("pkexec") else ["sudo", "-n"]
    return run(gate + cmd, **kw)


# ── profiles ────────────────────────────────────────────────────────────────

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
    return profiles.get("generic") or {
        "id": "generic", "name": "Generic CUPS Printer", "match": [".*"]
    }


# ── printer detection ───────────────────────────────────────────────────────

def detect_printers():
    """Return all printers lpinfo can see: USB, IPP, network, HP, Bluetooth."""
    _, out, _ = run(["lpinfo", "-v"])
    found = []
    profiles = load_profiles()

    for line in out.splitlines():
        _, _, uri = line.partition(" ")
        uri = uri.strip()
        if not uri:
            continue

        if uri.startswith("usb://"):
            path = urllib.parse.unquote(uri[6:].split("?")[0])
            vendor, _, model = path.partition("/")
            found.append({"uri": uri, "vendor": vendor, "model": model, "transport": "usb"})

        elif uri.startswith("dnssd://") or uri.startswith("mdns://"):
            label = urllib.parse.unquote(uri.split("//", 1)[1].split("._")[0])
            vendor, _, model = label.partition("/")
            found.append({"uri": uri, "vendor": vendor, "model": model or label, "transport": "network"})

        elif uri.startswith(("ipp://", "ipps://", "ipp+usb://")):
            # IPP/IPPS: hostname in path
            parsed = urllib.parse.urlparse(uri)
            host = parsed.hostname or ""
            model = parsed.path.strip("/").split("/")[-1] or host
            found.append({"uri": uri, "vendor": "", "model": model, "transport": "ipp"})

        elif uri.startswith(("socket://", "lpd://", "smb://")):
            parsed = urllib.parse.urlparse(uri)
            host = parsed.hostname or ""
            found.append({"uri": uri, "vendor": "", "model": host, "transport": "network"})

        elif uri.startswith("hp://") or uri.startswith("hpfax://"):
            path = urllib.parse.unquote(uri.split("//", 1)[1].split("?")[0])
            found.append({"uri": uri, "vendor": "HP", "model": path, "transport": "usb"})

        elif uri.startswith("bluetooth://"):
            found.append({"uri": uri, "vendor": "", "model": "Bluetooth printer", "transport": "bluetooth"})

    for f in found:
        f["profile"] = match_profile(f"{f['vendor']} {f['model']}", profiles)["id"]

    return found


def queues():
    """Return configured CUPS queues with name, uri, default flag."""
    _, out, _ = run(["lpstat", "-p"])
    names = re.findall(r"^printer (\S+)", out, re.M)
    uris  = dict(re.findall(r"device for (\S+): (\S+)", run(["lpstat", "-v"])[1]))
    m     = re.search(r"destination: (\S+)", run(["lpstat", "-d"])[1])
    default = m.group(1) if m else ""
    return [{"name": n, "uri": uris.get(n, ""), "default": n == default} for n in names]


# ── job queue ───────────────────────────────────────────────────────────────

def list_jobs(queue=None):
    """Return active + completed jobs via lpstat."""
    flags = ["-o"] + ([queue] if queue else []) + ["-l"]
    _, out, _ = run(["lpstat"] + flags, timeout=10)
    jobs = []
    cur = {}
    for line in out.splitlines():
        m = re.match(r"^(\S+)\s+(\S+)\s+(\d+)\s+(.+)$", line)
        if m and not line.startswith(" "):
            if cur:
                jobs.append(cur)
            cur = {
                "id":     m.group(1),
                "user":   m.group(2),
                "size":   int(m.group(3)),
                "time":   m.group(4).strip(),
                "file":   "",
                "status": "pending",
                "queue":  queue or m.group(1).rsplit("-", 1)[0],
                "pages":  "—",
            }
        elif line.strip().startswith("Status:") and cur:
            cur["status"] = line.split(":", 1)[1].strip().lower()
        elif re.match(r"^\s+Title:", line) and cur:
            cur["file"] = line.split(":", 1)[1].strip()
        elif re.match(r"^\s+Size:", line) and cur:
            try:
                cur["pages"] = str(int(line.split()[1]) // 1024) + " KB"
            except Exception:
                pass
    if cur:
        jobs.append(cur)

    # Also check for a simple one-liner format
    if not jobs:
        _, out2, _ = run(["lpstat", "-o"] + ([queue] if queue else []))
        for line in out2.splitlines():
            parts = line.split()
            if len(parts) >= 3:
                jid = parts[0]
                jobs.append({
                    "id":     jid,
                    "user":   parts[1] if len(parts) > 1 else "?",
                    "file":   " ".join(parts[3:]) if len(parts) > 3 else jid,
                    "queue":  jid.rsplit("-", 1)[0],
                    "size":   0,
                    "pages":  "—",
                    "status": "queued",
                    "time":   parts[2] if len(parts) > 2 else "",
                })

    return jobs


def cancel_job(job_id):
    """Cancel a print job by ID."""
    rc, out, err = run_priv(["cancel", job_id])
    return {"ok": rc == 0, "message": (err or out or "Cancelled.").strip()}


# ── drivers ─────────────────────────────────────────────────────────────────

def list_drivers():
    _, out, _ = run(["lpinfo", "-m"], timeout=120)
    return [tuple(l.split(None, 1)) if " " in l else (l, "") for l in out.splitlines() if l.strip()]


def find_driver(profile, drivers=None):
    drivers = drivers if drivers is not None else list_drivers()
    for hint in profile.get("driver_hints", []):
        for did, desc in drivers:
            if re.search(hint, f"{did} {desc}", re.I):
                return did
    # IPP Everywhere is the universal driverless fallback
    return next((d for d, _ in drivers if d in ("everywhere", "driverless")), None)


# ── distro detection ────────────────────────────────────────────────────────

def distro():
    """Return package manager name for this distro."""
    try:
        txt = Path("/etc/os-release").read_text().lower()
    except OSError:
        txt = ""
    # Order matters — check specifics before catch-alls
    for key, mgr in (
        ("arch",        "pacman"),
        ("cachyos",     "pacman"),
        ("manjaro",     "pacman"),
        ("endeavouros", "pacman"),
        ("garuda",      "pacman"),
        ("artix",       "pacman"),
        ("blackarch",   "pacman"),
        ("ubuntu",      "apt"),
        ("debian",      "apt"),
        ("linuxmint",   "apt"),
        ("popos",       "apt"),
        ("elementary",  "apt"),
        ("zorin",       "apt"),
        ("kali",        "apt"),
        ("lmde",        "apt"),
        ("neon",        "apt"),
        ("fedora",      "dnf"),
        ("rhel",        "dnf"),
        ("centos",      "dnf"),
        ("alma",        "dnf"),
        ("rocky",       "dnf"),
        ("nobara",      "dnf"),
        ("opensuse",    "zypper"),
        ("suse",        "zypper"),
        ("void",        "xbps"),
        ("alpine",      "apk"),
        ("gentoo",      "emerge"),
        ("nixos",       "nix"),
    ):
        if key in txt:
            return mgr
    # Fallback: check which manager is actually installed
    return next((m for m in ("pacman", "apt", "dnf", "zypper", "xbps-install", "apk", "emerge")
                 if shutil.which(m)), "unknown")


def package_commands(profile, mgr=None, helper=None):
    """Return [(argv, needs_root)] to install a profile's driver packages."""
    mgr = mgr or distro()
    pk = profile.get("packages", {})
    base = {
        "pacman": ["pacman", "-S", "--needed", "--noconfirm"],
        "apt":    ["apt-get", "install", "-y"],
        "dnf":    ["dnf",     "install", "-y"],
        "zypper": ["zypper",  "--non-interactive", "install"],
        "xbps":   ["xbps-install", "-y"],
        "apk":    ["apk",     "add"],
    }.get(mgr)
    cmds = [(base + pk[mgr], True)] if base and pk.get(mgr) else []
    if mgr == "pacman" and pk.get("aur"):
        helper = helper or next((h for h in ("paru", "yay", "trizen") if shutil.which(h)), None)
        if helper:
            cmds.append(([helper, "-S", "--needed", "--noconfirm"] + pk["aur"], False))
    return cmds


# ── queue setup ─────────────────────────────────────────────────────────────

def slug(s):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_") or "Printer"


def setup_queue(uri, profile, name=None, drivers=None):
    name = slug(name or profile.get("queue_name") or profile["name"])
    did  = find_driver(profile, drivers)
    if not did:
        return {
            "ok": False, "error": "no_driver",
            "message": f"No driver found for {profile['name']}. Install drivers first."
        }
    rc, out, err = run_priv([
        "lpadmin", "-p", name, "-E", "-v", uri, "-m", did,
        "-o", "printer-is-shared=false"
    ])
    if rc != 0:
        return {"ok": False, "error": "lpadmin", "message": (err or out).strip()}
    if not any(q["default"] for q in queues()):
        run_priv(["lpadmin", "-d", name])
    return {"ok": True, "queue": name, "driver": did}


def set_defaults(queue, options):
    """Write per-queue job defaults via lpadmin -p <queue> -o key=val …"""
    if not queue or not options:
        return {"ok": False, "message": "No queue or options provided."}
    args = ["lpadmin", "-p", queue]
    for k, v in options.items():
        if k and v is not None and str(v):
            args += ["-o", f"{k}={v}"]
    rc, out, err = run_priv(args)
    return {"ok": rc == 0, "message": (err or out or "Defaults saved.").strip()}


def remove_queue(name):
    """Delete a CUPS queue entirely."""
    rc, out, err = run_priv(["lpadmin", "-x", name])
    return {"ok": rc == 0, "message": (err or out or "Removed.").strip()}


# ── options / borderless ─────────────────────────────────────────────────────

def parse_options(text):
    res = []
    for line in text.splitlines():
        m = re.match(r"^([\w.\-]+)/([^:]*):\s*(.*)$", line)
        if m:
            ch      = m.group(3).split()
            default = next((c[1:] for c in ch if c.startswith("*")), ch[0] if ch else "")
            res.append({
                "key":     m.group(1),
                "label":   m.group(2).strip(),
                "choices": [c.lstrip("*") for c in ch],
                "default": default,
            })
    return res


def queue_options(queue):
    return parse_options(run(["lpoptions", "-p", queue, "-l"])[1])


def choices(opts, key):
    return next((o["choices"] for o in opts if o["key"].lower() == key.lower()), [])


def find_borderless(opts, size):
    return next(
        (c for c in choices(opts, "PageSize")
         if BORDER_RE.search(c) and c.lower().startswith(size.lower())),
        None
    )


def borderless_sizes(opts):
    return [c for c in choices(opts, "PageSize") if BORDER_RE.search(c)]


def build_print_args(queue, path, opts, size="A4", borderless=False, photo=False,
                     copies=1, grayscale=False, resolution=None, scale=False):
    args  = ["lp", "-d", queue, "-n", str(max(1, int(copies)))]
    notes = []

    if borderless:
        bl = find_borderless(opts, size)
        args += ["-o", f"PageSize={bl or size}", "-o", "fit-to-page"]
        notes.append(
            f"Borderless: {bl}." if bl else f"No borderless {size} in this driver — printed normally."
        )
    else:
        args += ["-o", f"PageSize={size}"]

    if photo:
        mts = choices(opts, "MediaType")
        mt  = next((c for r in ("glossy", "photo") for c in mts if re.search(r, c, re.I)), None)
        if mt:
            args += ["-o", f"MediaType={mt}"]
        args += ["-o", "print-quality=5"]

    if grayscale:
        args += ["-o", "ColorModel=Gray"]

    if resolution:
        args += ["-o", f"Resolution={resolution}"]

    if scale:
        args += ["-o", "fit-to-page"]

    return args + [str(path)], notes


def print_file(queue, path, **kw):
    args, notes = build_print_args(queue, path, queue_options(queue), **kw)
    rc, out, err = run(args)
    return {"ok": rc == 0, "message": (out or err).strip(), "notes": notes}


def probe_siblings(profile, uri, create=False, main=None, models=None):
    """Check sibling-model PPDs for borderless sizes; optionally create extra queues."""
    models = models if models is not None else list_drivers()
    main   = main or slug(profile.get("queue_name") or profile["name"])
    report = []
    for sib in profile.get("siblings", []):
        rx  = re.compile(
            rf"[^A-Za-z0-9]{re.escape(sib)}([^0-9]|$)|[ /-]{re.escape(sib)}[ _.-]", re.I
        )
        hit = next((d for d, desc in models if rx.search(f"{d} {desc}")), None)
        if not hit:
            report.append({"model": sib, "status": "no driver installed"})
            continue
        if run_priv(["lpadmin", "-p", "_probe", "-v", "socket://127.0.0.1:9", "-m", hit])[0] != 0:
            report.append({"model": sib, "status": "could not read"})
            continue
        bl = borderless_sizes(queue_options("_probe"))
        run_priv(["lpadmin", "-x", "_probe"])
        item = {"model": sib, "driver": hit, "borderless": bl, "status": "borderless" if bl else "none"}
        if bl and create and sib.lower() != main.lower():
            q  = f"{main}-{sib}"
            ok = run_priv([
                "lpadmin", "-p", q, "-E", "-v", uri, "-m", hit,
                "-o", "printer-is-shared=false"
            ])[0] == 0
            item["queue"] = q if ok else None
        report.append(item)
    return report


# ── maintenance ─────────────────────────────────────────────────────────────

def ink_levels(queue):
    out = run(["lpoptions", "-p", queue])[1]
    def g(k):
        m = re.search(rf"{k}=(?:'([^']*)'|\"([^\"]*)\"|(\S+))", out)
        raw = (m.group(1) or m.group(2) or m.group(3) or "") if m else ""
        return [x for x in raw.split(",") if x]
    names, levels, colors = g("marker-names"), g("marker-levels"), g("marker-colors")
    return [
        {
            "name":  n,
            "level": int(l) if l.lstrip("-").isdigit() else -1,
            "color": colors[i] if i < len(colors) else "",
        }
        for i, (n, l) in enumerate(zip(names, levels))
    ]


def _png(w, h, pixel):
    raw = b"".join(
        b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(w)) for y in range(h)
    )
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def make_test_png(path, kind="edge", w=620, h=877):
    """Pure-stdlib PNG. edge = gradient+frame to judge borderless bleed; nozzle = CMYK bars."""
    if kind == "nozzle":
        bars = [(0,255,255),(255,0,255),(255,255,0),(0,0,0),(255,0,0),(0,255,0),(0,0,255)]
        px   = lambda x, y: bars[(y * len(bars)) // h] if (x // 6) % 2 == 0 else (255, 255, 255)
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


# ── updates / community ──────────────────────────────────────────────────────

def fetch(url, timeout=12):
    with urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "printease/2"}), timeout=timeout
    ) as r:
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
        return {"ok": False, "message": "Not a git install. Re-run the installer to update."}
    rc, out, err = run(["git", "-C", str(ROOT), "pull", "--ff-only"], timeout=90)
    return {"ok": rc == 0, "message": (out or err).strip()}


def learn_draft(printer, borderless=None):
    model = printer.get("model", "Unknown")
    pid   = re.sub(r"[^a-z0-9]+", "-", f"{printer.get('vendor','')}-{model}".lower()).strip("-") or "new-printer"
    tok   = re.escape(model.split()[0]) if model else "."
    return {
        "id": pid, "name": f"{printer.get('vendor','')} {model}".strip(),
        "match": [tok], "driver_hints": [tok],
        "borderless_sizes": borderless or [], "packages": {}, "maintenance": [],
    }


def issue_url(draft, repo=None):
    q = urllib.parse.urlencode({
        "template": "printer-profile.yml",
        "title": f"Profile: {draft['name']}",
        "profile": json.dumps(draft, indent=2),
    })
    return f"https://github.com/{repo or REPO}/issues/new?{q}"


def unquote_name(n):
    return n if n.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".txt", ".ps")) else n + ".pdf"
