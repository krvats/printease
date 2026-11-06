<div align="center">

<img src="assets/banner.svg" alt="PrintEase" width="720">

**The VLC of printing for Linux.**  
Auto-detect, install drivers, set up queues, and print — all from one local web app. No CUPS knowledge required.

[![License: MIT](https://img.shields.io/badge/License-MIT-C8820A?style=flat-square&labelColor=0A0800)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-C8820A?style=flat-square&labelColor=0A0800&logo=python&logoColor=C8820A)](https://python.org)
[![CUPS](https://img.shields.io/badge/CUPS-2.x-C8820A?style=flat-square&labelColor=0A0800)](https://openprinting.github.io/cups/)
[![Arch Linux](https://img.shields.io/badge/Arch%20%2F%20CachyOS-supported-C8820A?style=flat-square&labelColor=0A0800)](https://archlinux.org)
[![GitHub Stars](https://img.shields.io/github/stars/krvats/printease?style=flat-square&color=C8820A&labelColor=0A0800)](https://github.com/krvats/printease/stargazers)

</div>

---

## Install in one command

```bash
curl -fsSL https://raw.githubusercontent.com/krvats/printease/main/install.sh | bash
```

Then start it:

```bash
printease          # starts the server and opens your browser
```

That's it. No config files, no manual CUPS setup, no reading man pages.

---

## What it does

Linux printing is broken by default. CUPS is powerful but its web interface is ancient, driver installation is distro-specific, and borderless printing requires hand-editing PPD files. PrintEase fixes all of that.

It runs a tiny local server (`127.0.0.1:8765`) and serves a web UI that talks to CUPS through a clean API. Everything stays on your machine — no cloud, no telemetry.

---

## Features

| | |
|---|---|
| **Auto-detection** | Finds USB and network printers via `lpinfo`, matches them against a profile database |
| **Driver install** | Generates the exact `pacman`/`apt`/`dnf` command for your printer and distro |
| **Queue setup** | Creates CUPS queues with the right driver in one click |
| **Drag-and-drop printing** | PDF, PNG, JPEG, PostScript, TXT — upload in browser, prints instantly |
| **Full CUPS options** | Paper size, print quality, duplex, resolution, grayscale — all exposed, nothing hidden |
| **Borderless printing** | Detects borderless sizes in the driver, probes sibling models for more |
| **Ink level monitoring** | Shows CMYK cartridge fill from driver-reported data |
| **Job queue** | View, cancel, and manage print jobs |
| **Job defaults** | Set per-queue defaults for all CUPS job options (matches the Job Options panel) |
| **Profile sync** | Pull updated printer profiles from GitHub without reinstalling |
| **Maintenance steps** | Nozzle check, head clean, edge bleed test — per printer profile |
| **No password prompts** | Installer sets up `sudoers` + polkit so `lpadmin` never interrupts you |

---

## Supported distros

| Distro family | Package manager | Auto-driver install |
|---|---|:---:|
| **Arch / CachyOS / Manjaro / EndeavourOS** | `pacman` + AUR | ✅ |
| **Ubuntu / Debian / Mint / Pop!_OS / Zorin** | `apt` | ✅ |
| **Fedora / RHEL / AlmaLinux / Rocky / Nobara** | `dnf` | ✅ |
| **openSUSE / SUSE** | `zypper` | ✅ |
| **Void Linux** | `xbps` | ✅ |
| **Alpine Linux** | `apk` | ✅ |
| **Gentoo** | `emerge` | ⚠️ manual |
| **NixOS** | `nix` | ⚠️ see [NixOS note](#nixos) |

---

## Supported printers

Profiles ship for the most common printer families. Any CUPS-compatible printer works via IPP Everywhere (driverless) even without a named profile.

| Brand | Coverage |
|---|---|
| **Epson** | L-series EcoTank (L3110, L3210, L3250, L3260, L4260, L4150, L4160, L6190, ET-series), Photo/SC series, XP/WF series |
| **HP** | Most LaserJet, DeskJet, OfficeJet, Envy, Smart Tank via HPLIP |
| **Canon** | PIXMA, MAXIFY, imageCLASS via BJNP/IPP |
| **Brother** | HL, DCP, MFC series via brlaser / IPP |
| **Generic** | IPP Everywhere driverless fallback — works for most printers made after 2016 |

**Don't see yours?** Run PrintEase → Updates → Contribute your printer. It generates a profile draft and opens a GitHub issue — you help one person, the profile ships to everyone.

---

## How it works

```
Your printer (USB/network)
        ↓
   lpinfo / lpstat          ← CUPS detects hardware
        ↓
   Profile database          ← matches vendor+model → driver hints + options
        ↓
   lpadmin                   ← creates the CUPS queue (via lp group, no sudo prompt)
        ↓
   PrintEase server           ← Python stdlib, runs on 127.0.0.1:8765
        ↓
   Browser UI                 ← drag file → POST /api/upload → POST /api/print → lp
```

No frameworks, no npm, no Electron. The server is pure Python stdlib. The UI is a single HTML file.

---

## Manual install (without curl)

```bash
git clone --depth 1 https://github.com/krvats/printease.git
cd printease
bash install.sh
```

Or run directly without installing:

```bash
python -m printease          # server starts, browser opens to localhost:8765
```

---

## Update

```bash
printease stop
cd ~/.local/share/printease-app
git pull --ff-only
printease start
```

Or from the UI: **Updates → Pull latest from GitHub**.

---

## Directory layout

```
printease/
├── printease/
│   ├── __init__.py        # version
│   ├── __main__.py        # entry point: python -m printease
│   ├── core.py            # all CUPS logic (stdlib only)
│   ├── server.py          # HTTP server + API dispatcher
│   └── ui/
│       └── index.html     # single-file web app (~60 KB)
├── profiles/
│   ├── index.json         # profile manifest (sha256 hashes for sync)
│   ├── epson-l3210.json
│   ├── hp.json
│   ├── canon.json
│   ├── brother.json
│   └── generic.json       # IPP Everywhere fallback
├── assets/
│   ├── banner.svg
│   └── icon.svg
├── install.sh
└── README.md
```

---

## API (for integrators)

The server speaks plain JSON over HTTP, token-authenticated against localhost only.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/printers` | Detected hardware |
| GET | `/api/queues` | Configured CUPS queues |
| GET | `/api/options?queue=` | CUPS options (PageSize, MediaType, etc.) |
| GET | `/api/ink?queue=` | Ink/toner levels |
| GET | `/api/jobs?queue=` | Active + completed jobs |
| POST | `/api/setup` | Create a CUPS queue |
| POST | `/api/upload` | Upload a file for printing |
| POST | `/api/print` | Send a print job |
| POST | `/api/cancel` | Cancel a job |
| POST | `/api/set-defaults` | Write per-queue job defaults |
| POST | `/api/test` | Print a nozzle/edge test page |
| POST | `/api/sync` | Sync profiles from GitHub |
| POST | `/api/probe` | Probe sibling drivers for borderless sizes |

The token is injected into the UI at startup (`__TOKEN__` → `secrets.token_hex(32)`). External access is blocked at the Host header level — only `127.0.0.1` and `localhost` are accepted.

---

## Contributing a printer profile

If your printer isn't in the database, you can add it in about 5 minutes.

A profile is a JSON file in `profiles/`. Minimal example:

```json
{
  "id": "epson-l3210",
  "name": "Epson L3210 Series",
  "match": ["L3210", "L3200"],
  "driver_hints": ["epson.*escpr", "escpr2"],
  "siblings": ["L3250", "L3260", "L4260"],
  "packages": {
    "pacman": [],
    "aur": ["epson-inkjet-printer-escpr2"],
    "apt": ["printer-driver-escpr"],
    "dnf": ["epson-inkjet-printer-escpr"]
  },
  "maintenance": [
    {
      "title": "Head cleaning",
      "how": "Hold the ink button for 3 seconds. Consumes ink."
    }
  ],
  "priority": 10
}
```

Fields:

| Field | Required | Description |
|---|:---:|---|
| `id` | ✅ | Slug, lowercase, hyphens only |
| `name` | ✅ | Human-readable printer name |
| `match` | ✅ | Regex patterns matched against vendor+model string |
| `driver_hints` | — | Regex patterns matched against `lpinfo -m` output |
| `siblings` | — | Related models that share the ink system (for borderless probe) |
| `packages` | — | Packages to install per package manager |
| `maintenance` | — | `{title, how}` steps shown in Maintenance tab |
| `priority` | — | Higher wins when multiple profiles match (default 0) |

**To submit:** run PrintEase → Updates → Contribute your printer. It pre-fills a GitHub issue with a draft profile from your detected hardware.

---

## NixOS

PrintEase's one-line installer doesn't work on NixOS. Add this to your `configuration.nix`:

```nix
services.printing = {
  enable = true;
  drivers = [ pkgs.epson-escpr2 pkgs.hplip ];  # adjust for your printer
};
services.avahi = { enable = true; nssmdns4 = true; };
```

Then clone the repo and run `python -m printease` manually.

---

## Why not just use system-config-printer / GNOME printer settings?

Those tools work for simple cases. PrintEase is for when you need:
- Borderless printing (they don't expose it)
- Specific paper sizes (most hide them)
- Sibling driver probing (unique to PrintEase)
- Ink levels without opening a separate app
- A repeatable, scriptable setup you can run on a fresh install

---

## License

[MIT](LICENSE) — do whatever you want with it.

---

<div align="center">

Made with frustration at 2am after the third printer setup that week.

**[⭐ Star it if it saved you time](https://github.com/krvats/printease)**

</div>
