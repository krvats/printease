import json, os, subprocess, sys, tempfile, threading, unittest, urllib.request
from pathlib import Path
R = Path(__file__).resolve().parent.parent
TMP = tempfile.mkdtemp()
os.environ.update(PATH=f"{R/'tests/fakebin'}:{os.environ['PATH']}", FAKECUPS_DIR=f"{TMP}/cups",
                  PRINTEASE_HOME=f"{TMP}/home", PRINTEASE_NO_PRIV="1")
sys.path.insert(0, str(R))
from printease import core, server  # noqa: E402


class T(unittest.TestCase):
    def test_profiles_valid(self):
        for f in (R / "profiles").glob("*.json"):
            if f.name != "index.json":
                self.assertTrue(core.validate_profile(json.loads(f.read_text())), f.name)

    def test_index_fresh(self):
        self.assertEqual(subprocess.run([sys.executable, str(R / "tools/make_index.py"), "--check"]).returncode, 0)

    def test_installer_syntax(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(R / "install.sh")]).returncode, 0)

    def test_match(self):
        self.assertEqual(core.match_profile("EPSON L3210 Series")["id"], "epson-l3210")
        self.assertEqual(core.match_profile("Brother HL-1110")["id"], "brother")
        self.assertEqual(core.match_profile("Zzz Unknown")["id"], "generic")

    def test_detect_setup_print(self):
        p = core.detect_printers()[0]
        self.assertEqual((p["transport"], p["profile"]), ("usb", "epson-l3210"))
        prof = core.load_profiles()[p["profile"]]
        r = core.setup_queue(p["uri"], prof)
        self.assertTrue(r["ok"], r)
        qs = core.queues()
        self.assertEqual(qs[0]["name"], "L3210"); self.assertTrue(qs[0]["default"])
        opts = core.queue_options("L3210")
        self.assertEqual(core.find_borderless(opts, "A4"), "A4.Borderless")
        res = core.print_file("L3210", R / "README.md", size="A4", borderless=True, photo=True)
        self.assertTrue(res["ok"])
        log = Path(os.environ["FAKECUPS_DIR"], "jobs.log").read_text()
        self.assertIn("PageSize=A4.Borderless", log); self.assertIn("MediaType=Glossy", log)
        self.assertEqual(core.ink_levels("L3210")[0]["level"], 80)

    def test_probe(self):
        prof = core.load_profiles()["epson-l3210"]
        rep = {x["model"]: x for x in core.probe_siblings(prof, "usb://x", create=True)}
        self.assertEqual(rep["L3250"]["queue"], "L3210-L3250")
        self.assertEqual(rep["L3150"]["status"], "none")
        self.assertEqual(rep["L1210"]["status"], "no driver installed")

    def test_no_driver(self):
        r = core.setup_queue("usb://x", {"name": "X", "driver_hints": ["nomatch"]}, drivers=[])
        self.assertEqual(r["error"], "no_driver")

    def test_png(self):
        p = Path(TMP, "t.png"); core.make_test_png(p, "edge", 40, 60)
        self.assertEqual(p.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_sync(self):
        import hashlib
        blob = json.dumps({"id": "newp", "name": "New", "match": ["New"]}).encode()
        idx = json.dumps({"profiles": [{"file": "newp.json", "sha256": hashlib.sha256(blob).hexdigest()},
                                       {"file": "../evil.json", "sha256": "0"}]}).encode()
        r = core.sync_profiles(lambda u: idx if u.endswith("index.json") else blob, repo="a/b")
        self.assertEqual(r["updated"], ["newp.json"])
        self.assertIn("newp", core.load_profiles())

    def test_bad_sync(self):
        r = core.sync_profiles(lambda u: (_ for _ in ()).throw(OSError("offline")), repo="a/b")
        self.assertFalse(r["ok"])

    def test_server(self):
        srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        self.assertIn("PrintEase", urllib.request.urlopen(base + "/").read().decode())
        with self.assertRaises(Exception):
            urllib.request.urlopen(base + "/api/status")
        rq = urllib.request.Request(base + "/api/status", headers={"X-Token": server.TOKEN})
        self.assertIn("printers", json.loads(urllib.request.urlopen(rq).read()))
        srv.shutdown()

    def test_draft(self):
        d = core.learn_draft({"vendor": "ACME", "model": "X100 Series"})
        self.assertTrue(core.validate_profile(d)); self.assertIn("issues/new", core.issue_url(d))


if __name__ == "__main__":
    unittest.main()
