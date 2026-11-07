# Contributing to PrintEase

## ⚠️ **The one-command rule**
**Everything must install with ONE command:** `curl -fsSL https://raw.githubusercontent.com/krvats/printease/main/install.sh | bash`.
**Any new dependency, file or feature MUST be wired into `install.sh`.** PRs that need extra manual steps will not be merged.

## Add a printer profile
1. Copy `profiles/generic.json` to `profiles/<id>.json` (id: lowercase letters, digits, dashes).
2. Fill `match` (regexes against the USB/vendor/model text), `driver_hints` (regexes against `lpinfo -m`), `packages` per distro, `maintenance` tips.
3. `python3 tools/make_index.py` (updates the sha256 manifest used by Sync).
4. `python3 -m unittest discover -s tests`

## Dev setup
No dependencies. Run without CUPS using the fakes:
```bash
export PATH=$PWD/tests/fakebin:$PATH FAKECUPS_DIR=/tmp/fc PRINTEASE_HOME=/tmp/pe PRINTEASE_NO_PRIV=1
python3 -m printease --no-open --keep-alive
```
Code style: Python stdlib only, `bash -n` + `shellcheck` clean installer.
