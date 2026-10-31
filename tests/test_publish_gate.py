"""Negative + positive tests for the publish gate. Synthetic fixtures only -
no real picks, messages or private data."""
import json, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import publish_gate as gate


def build_repo(root: Path, fp_source="reviewed"):
    (root / "scripts").mkdir(parents=True)
    (root / "brand/Templates").mkdir(parents=True)
    (root / "fonts").mkdir(parents=True)
    (root / "data/state").mkdir(parents=True)
    (root / "scripts/render_brand_templates.py").write_text(f"# renderer {fp_source}")
    (root / "brand/Templates/t.dc.html").write_text(f"<html>{fp_source}</html>")
    (root / "fonts/f.ttf").write_bytes(fp_source.encode() * 10)
    return gate.compute_renderer_fingerprint(root)


def build_package(root: Path, renderer_fp) -> Path:
    pkg = root / "data/review/2026-01-01_research_Test_Multi"
    pkg.mkdir(parents=True)
    (pkg / "manifest.json").write_text(json.dumps(
        {"files": {}, "renderer_fingerprint": renderer_fp}))
    return pkg


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fp = build_repo(self.root)
        (self.root / gate.PIN_PATH).write_text(json.dumps(
            {"renderer_fingerprint": self.fp, "pinned_from": "test"}))
        self.pkg = build_package(self.root, self.fp)

    def tearDown(self):
        self.tmp.cleanup()

    def attempt(self, approval="synthetic-approval-ref"):
        return gate.assert_publish_allowed(
            "2026-01-01_research_Test_Multi", str(self.pkg), str(self.root),
            approval, "publish-multi", ["telegram", "instagram_story"])

    def test_happy_path_records_hashes_only(self):
        rec = self.attempt()
        blob = json.dumps(rec)
        self.assertNotIn("synthetic-approval-ref", blob)   # privacy
        self.assertEqual(rec["renderer_fingerprint"], self.fp)
        self.assertEqual(len(rec["artifact_sha256"]), 64)
        self.assertNotIn("wa-", blob)

    def test_stale_template_blocked(self):
        other = dict(json.loads((self.root / gate.PIN_PATH).read_text()))
        other["renderer_fingerprint"] = "0" * 64           # pin moved on
        (self.root / gate.PIN_PATH).write_text(json.dumps(other))
        with self.assertRaises(SystemExit):
            self.attempt()

    def test_unstamped_package_blocked(self):
        m = json.loads((self.pkg / "manifest.json").read_text())
        del m["renderer_fingerprint"]                       # wrong assets
        (self.pkg / "manifest.json").write_text(json.dumps(m))
        with self.assertRaises(SystemExit):
            self.attempt()

    def test_missing_approval_blocked(self):
        with self.assertRaises(SystemExit):
            self.attempt(approval="")
        with self.assertRaises(SystemExit):
            self.attempt(approval="   ")

    def test_missing_pin_fails_closed(self):
        (self.root / gate.PIN_PATH).unlink()
        with self.assertRaises(AssertionError):
            self.attempt()

    def test_artifact_binds_pick_assets_audience(self):
        a = self.attempt()
        b = gate.assert_publish_allowed(
            "2026-01-01_research_Other", str(self.pkg), str(self.root),
            "synthetic-approval-ref", "publish-multi", ["telegram"])
        self.assertNotEqual(a["artifact_sha256"], b["artifact_sha256"])

    def test_record_written_under_data_approvals(self):
        rec = self.attempt()
        path = gate.write_approval_record(self.root, rec)
        self.assertTrue(Path(path).is_file())
        self.assertIn("data/approvals", path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
