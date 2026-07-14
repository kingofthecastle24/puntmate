import os, sys, json, shutil, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from manifest import build_manifest, verify_manifest, write_manifest, load_manifest
from workflow_state import transition, load_state, InvalidTransitionError, GENERATED, PREVIEW_READY, \
    AWAITING_APPROVAL, APPROVED, REJECTED, PUBLISHING, PUBLISHED


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_manifest_roundtrip_ok(self):
        with open(os.path.join(self.tmp, "a.txt"), "w") as f:
            f.write("hello")
        manifest = build_manifest(self.tmp, ["a.txt"])
        ok, mismatches = verify_manifest(manifest, self.tmp)
        self.assertTrue(ok)
        self.assertEqual(mismatches, [])

    def test_manifest_detects_tampering(self):
        with open(os.path.join(self.tmp, "a.txt"), "w") as f:
            f.write("hello")
        manifest = build_manifest(self.tmp, ["a.txt"])
        with open(os.path.join(self.tmp, "a.txt"), "w") as f:
            f.write("TAMPERED")
        ok, mismatches = verify_manifest(manifest, self.tmp)
        self.assertFalse(ok)
        self.assertTrue(len(mismatches) == 1)

    def test_manifest_detects_missing_file(self):
        with open(os.path.join(self.tmp, "a.txt"), "w") as f:
            f.write("hello")
        manifest = build_manifest(self.tmp, ["a.txt"])
        os.remove(os.path.join(self.tmp, "a.txt"))
        ok, mismatches = verify_manifest(manifest, self.tmp)
        self.assertFalse(ok)


class WorkflowStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_happy_path_transitions(self):
        pid = "2026-07-15_test"
        transition(self.tmp, pid, GENERATED)
        transition(self.tmp, pid, PREVIEW_READY)
        transition(self.tmp, pid, AWAITING_APPROVAL)
        transition(self.tmp, pid, APPROVED)
        transition(self.tmp, pid, PUBLISHING)
        rec = transition(self.tmp, pid, PUBLISHED)
        self.assertEqual(rec["state"], PUBLISHED)

    def test_rejected_to_published_is_blocked(self):
        pid = "2026-07-15_test2"
        transition(self.tmp, pid, GENERATED)
        transition(self.tmp, pid, PREVIEW_READY)
        transition(self.tmp, pid, AWAITING_APPROVAL)
        transition(self.tmp, pid, REJECTED)
        with self.assertRaises(InvalidTransitionError):
            transition(self.tmp, pid, PUBLISHED)

    def test_first_transition_must_be_generated(self):
        pid = "2026-07-15_test3"
        with self.assertRaises(InvalidTransitionError):
            transition(self.tmp, pid, APPROVED)

    def test_cannot_skip_states(self):
        pid = "2026-07-15_test4"
        transition(self.tmp, pid, GENERATED)
        with self.assertRaises(InvalidTransitionError):
            transition(self.tmp, pid, APPROVED)  # skipping PREVIEW_READY/AWAITING_APPROVAL


if __name__ == "__main__":
    unittest.main()
