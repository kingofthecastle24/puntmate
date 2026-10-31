"""Gate tests: integrity, review hold path detection, attestation honesty.
Synthetic fixtures only - no real picks, messages or private data."""
import json, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import publish_gate as gate


def build_repo(root: Path, marker="reviewed"):
    (root / "scripts").mkdir(parents=True)
    (root / "brand/Templates").mkdir(parents=True)
    (root / "fonts").mkdir(parents=True)
    (root / "data/state").mkdir(parents=True)
    (root / "scripts/render_brand_templates.py").write_text(f"# renderer {marker}")
    (root / "brand/Templates/t.dc.html").write_text(f"<html>{marker}</html>")
    (root / "fonts/f.ttf").write_bytes(marker.encode() * 10)
    return gate.compute_renderer_fingerprint(root)


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.fp = build_repo(self.root)
        (self.root / gate.PIN_PATH).write_text(json.dumps(
            {"renderer_fingerprint": self.fp, "pinned_from": "test"}))
        pkg = self.root / "data/review/2026-01-01_research_Test_Multi"
        pkg.mkdir(parents=True)
        (pkg / "manifest.json").write_text(json.dumps({"files": {}}))
        self.pkg = pkg

    def tearDown(self):
        self.tmp.cleanup()

    # integrity
    def test_pin_match_passes(self):
        self.assertEqual(gate.assert_pin_matches(self.root), self.fp)

    def test_unbumped_template_change_blocked(self):
        (self.root / "brand/Templates/t.dc.html").write_text("<html>changed</html>")
        with self.assertRaises(SystemExit):
            gate.assert_pin_matches(self.root)

    def test_missing_pin_fails_closed(self):
        (self.root / gate.PIN_PATH).unlink()
        with self.assertRaises(AssertionError):
            gate.assert_pin_matches(self.root)

    # review hold path detection
    def test_renderer_pr_detected(self):
        hit = gate.renderer_paths_touched(
            ["scripts/render_brand_templates.py", "README.md"])
        self.assertEqual(hit, ["scripts/render_brand_templates.py"])
        self.assertTrue(gate.renderer_paths_touched(["fonts/Archivo-Black.ttf"]))
        self.assertTrue(gate.renderer_paths_touched(["brand/Templates/x.dc.html"]))

    def test_non_renderer_pr_ignored(self):
        self.assertFalse(gate.renderer_paths_touched(
            ["README.md", ".github/workflows/standin_research.yml",
             "scripts/fetch_odds.py", "data/state/x.json"]))

    # attestation honesty
    def test_empty_attestation_blocked(self):
        for bad in ("", "   ", None):
            with self.assertRaises(SystemExit):
                gate.record_attestation("p", str(self.pkg), "publish-multi",
                                        ["telegram"], bad or "")

    def test_attestation_hashes_only_and_binds_scope(self):
        rec = gate.record_attestation(
            "2026-01-01_research_Test_Multi", str(self.pkg),
            "publish-multi", ["telegram", "instagram_story"],
            "synthetic-reference-123")
        blob = json.dumps(rec)
        self.assertNotIn("synthetic-reference-123", blob)
        self.assertEqual(rec["type"], "operator_attestation")
        self.assertIn("does not verify", rec["note"])
        other = gate.record_attestation(
            "2026-01-01_research_Test_Multi", str(self.pkg),
            "publish-multi", ["telegram"], "synthetic-reference-123")
        self.assertNotEqual(rec["artifact_sha256"], other["artifact_sha256"])

    def test_attestation_binds_actual_package_bytes(self):
        rec1 = gate.record_attestation(
            "p", str(self.pkg), "publish-multi", ["telegram"], "ref")
        (self.pkg / "manifest.json").write_text(json.dumps({"files": {"x": 1}}))
        rec2 = gate.record_attestation(
            "p", str(self.pkg), "publish-multi", ["telegram"], "ref")
        self.assertNotEqual(rec1["package_manifest_sha256"],
                            rec2["package_manifest_sha256"])

    def test_record_written(self):
        rec = gate.record_attestation("p", str(self.pkg), "publish-multi",
                                      ["telegram"], "ref")
        self.assertTrue(Path(gate.write_attestation_record(self.root, rec)).is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
