#!/usr/bin/env python3
"""Fake CUPS CLI for tests: lpinfo, lpstat, lpadmin, lpoptions, lp."""
import json, os, sys
from pathlib import Path
D = Path(os.environ["FAKECUPS_DIR"]); D.mkdir(parents=True, exist_ok=True)
F = D / "state.json"
st = json.loads(F.read_text()) if F.exists() else {"q": {}, "default": None}
cmd, a = sys.argv[1], sys.argv[2:]
arg = lambda f: a[a.index(f) + 1] if f in a else None
if cmd == "lpinfo":
    if "-v" in a:
        print("network socket\ndirect usb://EPSON/L3210%20Series?serial=X1")
    else:
        print("escpr2-epson-l3210.ppd Epson L3210 Series\nescpr2-epson-l3250.ppd Epson L3250 Series\n"
              "escpr2-epson-l3150.ppd Epson L3150 Series\neverywhere IPP Everywhere")
elif cmd == "lpadmin":
    if arg("-x"): st["q"].pop(arg("-x"), None)
    elif arg("-p"): st["q"][arg("-p")] = {"uri": arg("-v") or "", "ppd": arg("-m") or ""}
    elif arg("-d"): st["default"] = arg("-d")
elif cmd == "lpstat":
    for n in st["q"]:
        if "-p" in a: print(f"printer {n} is idle.  enabled since Mon")
        if "-v" in a: print(f"device for {n}: {st['q'][n]['uri']}")
    if "-d" in a: print(f"system default destination: {st['default']}" if st["default"] else "no system default destination")
elif cmd == "lpoptions":
    q = arg("-p")
    if "-l" in a:
        bl = "l3150" not in st["q"].get(q, {}).get("ppd", "")
        print("PageSize/Media Size: *A4 Letter 4x6" + (" A4.Borderless 4x6.Borderless" if bl else ""))
        print("MediaType/Media Type: *Plain Glossy")
    else:
        print("marker-names=Black,Cyan marker-levels=80,50 marker-colors=#000000,#00ffff")
elif cmd == "lp":
    with open(D / "jobs.log", "a") as f: f.write(" ".join(a) + "\n")
    print("request id is Q-1 (1 file(s))")
F.write_text(json.dumps(st))
