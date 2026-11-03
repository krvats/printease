<div align="center">

<img src="https://upload.wikimedia.org/wikipedia/commons/9/97/The_Earth_seen_from_Apollo_17.jpg" width="220" alt="The Blue Marble, photographed by the Apollo 17 crew (NASA)">

# 🖨️ PrintEase

### Mission control for your printer. No terminal. No tears.

Plug in, click **Set up**, print. Built first for the **Epson L3210**, extensible to **any CUPS printer**.

[![License: MIT](https://img.shields.io/badge/license-MIT-4fa3ff?style=for-the-badge)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/krvats/printease/ci.yml?style=for-the-badge&label=tests&color=7cf2c9)](https://github.com/krvats/printease/actions)
[![Python](https://img.shields.io/badge/python-3.8%2B-4fa3ff?style=for-the-badge&logo=python&logoColor=white)](#)
[![Dependencies](https://img.shields.io/badge/dependencies-zero-7cf2c9?style=for-the-badge)](#)
[![Linux](https://img.shields.io/badge/linux-Arch%20%7C%20Debian%20%7C%20Fedora%20%7C%20openSUSE-0c2a66?style=for-the-badge&logo=linux&logoColor=white)](#)

<sub>Hero image: *The Blue Marble*, Apollo 17 crew, NASA (public domain), via Wikimedia Commons.</sub>

</div>

---

## 🚀 Install (one command)

```bash
curl -fsSL https://raw.githubusercontent.com/krvats/printease/main/install.sh | bash
```

Then open **PrintEase** from your app menu (or the Desktop icon). That's it, **no terminal needed after install**.

> **Replace `krvats`** with your GitHub username in this README, `install.sh` and `profiles/` URLs after you push.

## ✨ Features

| | Feature | What it does |
|---|---|---|
| 🔌 | **Auto-detect** | Finds your USB/network printer and loads the matching JSON profile |
| 🛠️ | **One-click setup** | Installs drivers, creates the CUPS queue, sets it as default |
| 🖼️ | **Borderless** | Probes the driver (PPD) for edge-to-edge sizes, prints an edge test, can try sibling-model drivers |
| 🧰 | **Maintenance** | Ink levels (when reported), nozzle-check pattern, head-cleaning tips per model |
| 🔄 | **Self-updating** | New printer profiles sync from this repo, **no reinstall** |
| 🧠 | **Learns new printers** | Unknown printer? One click drafts a profile and opens a GitHub issue |
| 🪶 | **Zero dependencies** | Python standard library + your browser. No pip, no PySide, no tkinter |
| 🔒 | **Private** | Local server on `127.0.0.1` with a per-session token. Nothing leaves your machine |

## 🧭 The app

| Tab | Use it to |
|---|---|
| **Printer** | See detected printers and queues, install drivers, set up |
| **Print** | Pick a file, paper size, copies, photo quality, borderless |
| **Borderless** | Edge test + sibling-driver probe |
| **Maintenance** | Ink bars, nozzle pattern, cleaning steps |
| **Updates** | Sync profiles, update app, star the repo ⭐ |

## 🖨️ Supported printers

| Printer | Status |
|---|---|
| **Epson L3210** | ✅ First-class (drivers, borderless probe, maintenance) |
| Other Epson inkjets (EcoTank etc.) | 🟢 Epson profile |
| HP, Brother, Canon | 🟡 Basic profiles (drivers + tips) |
| Anything else CUPS can see | 🟡 Generic profile, IPP Everywhere fallback |

Yours missing? [Add it in 2 minutes](CONTRIBUTING.md) or use **Updates → Contribute this printer**.

## ⚠️ Honest limits

- Epson documents borderless for **4x6 in photo paper** on the L3210; A4 borderless may not exist in every driver version. The Borderless tab tells you what *your* driver offers.
- A sibling model's driver can give slightly different colours or margins. Your original queue is never modified; remove extras with `sudo lpadmin -x L3210-L3250`.

## 🤝 Contribute

Profiles are plain JSON in [`profiles/`](profiles). Add one, run `python3 tools/make_index.py`, open a PR. Read [CONTRIBUTING.md](CONTRIBUTING.md).

> **Rule for every change:** any new dependency, file or feature **must be wired into the single `install.sh`** so the one-command install always works.

## ⭐ Star this repo or the printer jams

Nobody has *proven* it won't. Hit the star. 🖨️💥

## 📄 License

MIT. See [LICENSE](LICENSE).
