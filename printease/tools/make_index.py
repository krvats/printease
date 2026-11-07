#!/usr/bin/env python3
"""Regenerate profiles/index.json (sha256 manifest). CI fails if stale."""
import hashlib, json, pathlib, sys
d = pathlib.Path(__file__).resolve().parent.parent / "profiles"
items = [{"file": f.name, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
         for f in sorted(d.glob("*.json")) if f.name != "index.json"]
new = json.dumps({"profiles": items}, indent=2) + "\n"
idx = d / "index.json"
if "--check" in sys.argv:
    sys.exit(0 if idx.exists() and idx.read_text() == new else "profiles/index.json is stale: run tools/make_index.py")
idx.write_text(new); print(f"{len(items)} profiles indexed")
