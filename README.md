# PrintEase

A local web UI for managing printers on Linux. Wraps CUPS so you can add printers,
send print jobs, check ink levels, and manage job defaults without touching the terminal.

---

## Requirements

- Linux (any mainstream distro)
- CUPS 2.x or later
- Python 3.8 or later
- A browser (opens automatically)

---

## Install — one command

```bash
curl -fsSL https://raw.githubusercontent.com/krvats/printease/main/install.sh | bash
```

The installer:
1. Installs CUPS, Python 3, polkit and Avahi via your distro's package manager  
2. Starts CUPS  
3. Downloads PrintEase  
4. Shows driver guidance for your distro  
5. Creates a launcher and app-menu / Desktop entry  

**Supported distros**: Arch, CachyOS, Manjaro, EndeavourOS, Garuda, Artix, Ubuntu,
Debian, Linux Mint, Pop!_OS, Elementary, Zorin, Kali, Fedora, RHEL, CentOS, AlmaLinux,
Rocky, Nobara, openSUSE, SUSE, Void, Alpine, NixOS (manual step), Gentoo.

---

## Running

```bash
printease          # from anywhere after install
# or
python3 -m printease
```

A browser tab opens at `http://127.0.0.1:8765`.

---

## Manual install (without curl)

```bash
git clone https://github.com/krvats/printease.git
cd printease
bash install.sh
```

---

## Features

| Section | What it does |
|---|---|
| Dashboard | Printer list, active job count, distro info |
| Print | Send a file to any configured printer |
| Job Queue | View and cancel active / recent jobs |
| Printers | Discover USB and network printers, add / remove queues |
| Printer Options | View all CUPS capabilities for the selected printer |
| Job Defaults | Set per-printer default paper size, sides, color, quality |
| Ink Levels | Cartridge levels (IPP / vendor drivers only) |
| Maintenance | Nozzle check, head clean, test page, remove queue |
| Updates | Current version and update command |

---

## Security

PrintEase listens only on `127.0.0.1` (localhost). Every API call requires a
per-session token; requests from other hosts are rejected. The app never exposes
your printer or files to the network.

---

## Printer drivers

IPP Everywhere (driverless) is built into CUPS 2.x and covers most modern printers.
If your printer needs a vendor driver, see the guidance printed by the installer,
or use **Maintenance → Driver packages** inside the app.

---

## License

MIT
