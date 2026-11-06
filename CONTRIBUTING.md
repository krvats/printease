# Contributing to PrintEase

Thanks for helping make Linux printing less painful.

The most useful thing you can do is **add a printer profile** — it means every future user with that printer gets auto-detected and set up in one click. This guide walks you through it in under 10 minutes.

---

## The fastest path: use PrintEase itself

1. Connect your printer.
2. Open PrintEase → **Updates** → **Contribute your printer**.
3. It generates a draft profile from the detected hardware and opens a pre-filled GitHub issue.
4. Fill in any missing fields (packages for other distros, sibling models), submit.

If your printer isn't detected at all, do it manually below.

---

## Writing a profile manually

Create `profiles/<brand>-<model>.json`. Use the slug `brand-model`, lowercase, hyphens only.

### Full schema

```json
{
  "id": "epson-l3210",
  "name": "Epson L3210 Series",
  "match": ["L3210", "L3200", "L32[0-9]{2}"],
  "driver_hints": ["epson.*escpr2?", "escpr"],
  "siblings": ["L3250", "L3260", "L4260"],
  "packages": {
    "pacman": [],
    "aur": ["epson-inkjet-printer-escpr2"],
    "apt": ["printer-driver-escpr"],
    "dnf": ["epson-inkjet-printer-escpr"],
    "zypper": ["epson-inkjet-printer-escpr"],
    "xbps": []
  },
  "ppd_options": {
    "PageSize": "A4"
  },
  "maintenance": [
    {
      "title": "Head cleaning",
      "how": "Hold the ink (droplet) button on the printer for 3 seconds. This flushes the nozzles. Consumes ink — don't run more than twice in a row without a nozzle check in between."
    },
    {
      "title": "Nozzle check",
      "how": "Print the nozzle check pattern from PrintEase → Maintenance. Gaps mean a clean cycle is needed."
    }
  ],
  "notes": "EcoTank printer. Keep all tanks above 20% before running head cleaning.",
  "priority": 10
}
```

### Field reference

| Field | Type | Required | Description |
|---|---|:---:|---|
| `id` | string | ✅ | Unique slug — lowercase letters, digits, hyphens. Must match the filename. |
| `name` | string | ✅ | Human-readable name shown in the UI. |
| `match` | string[] | ✅ | Regex patterns matched against `vendor + " " + model` from `lpinfo -l -v`. Case-insensitive. |
| `driver_hints` | string[] | — | Regex patterns matched against PPD filenames in `lpinfo -m` output. First match wins. |
| `siblings` | string[] | — | Model numbers that share the ink system (used by the borderless probe to find extra page sizes). |
| `packages` | object | — | Packages per package manager. Empty list `[]` = no packages needed. Omit keys for unsupported managers. |
| `ppd_options` | object | — | Default PPD key/value options set when creating the queue. |
| `maintenance` | object[] | — | `{title: string, how: string}` steps shown in Maintenance tab. |
| `notes` | string | — | Free-form notes shown under the maintenance steps. |
| `priority` | number | — | When multiple profiles match, highest priority wins. Default `0`. Use `10` for exact model matches, `1` for family fallbacks. |

### Tips for good match patterns

- Match the model number only, not the brand — the brand is matched separately: `"L3210"` not `"Epson L3210"`.
- Use regex ranges for model families: `"L3[12][0-9]{2}"` matches L3100–L3299.
- Test your regex: `python -c "import re; print(re.search('L3210', 'EPSON L3210 Series', re.I))"`.
- If you're unsure, run `lpinfo -l -v` on your machine and copy the exact model string.

---

## Running the tests locally

```bash
# Syntax + import check
python -m py_compile printease/core.py printease/server.py

# Profile validation
python - << 'EOF'
import json, pathlib, re
for f in pathlib.Path("profiles").glob("*.json"):
    if f.name == "index.json": continue
    data = json.loads(f.read_text())
    assert {"id","name","match"} <= data.keys(), f"{f.name}: missing required fields"
    print(f"✓ {f.name}")
EOF

# ShellCheck (install it first: pacman -S shellcheck / apt install shellcheck)
shellcheck install.sh
```

---

## Submitting a PR

1. Fork the repo.
2. Create a branch: `git checkout -b profile/epson-l4260`.
3. Add your profile to `profiles/`.
4. Run the tests above.
5. Open a PR. The CI will validate automatically.

For bugfixes or features, describe what breaks and what you changed. Keep PRs focused — one issue per PR.

---

## What we don't accept

- Changes that add external dependencies (the server must stay pure Python stdlib).
- Profiles with untested `match` patterns (please test on real hardware or `lpinfo` output).
- UI changes that require a build step.
- Anything that phones home, collects data, or requires internet at runtime.

---

## Code style

No linter config enforced — just keep it consistent with the surrounding code. The whole codebase is intentionally minimal: readable Python, no frameworks, no magic.
