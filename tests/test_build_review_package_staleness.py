"""
Tests for build_review_package.py's stale-latest_run.json guard (2026-10-11,
external audit item 2: "refuse stale latest_run.json/artifacts downstream").
generate.yml runs main.py and build_review_package.py in the same workflow
run, so a mismatched run_id means this file is leftover from a different
run and must never be silently frozen into a review package.
"""
import os, sys, json, shutil, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import build_review_package as brp


class StaleRunDataGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.tmp, "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self._orig = (brp.REPO_ROOT, brp.LATEST_RUN_PATH, brp.CARDS_DIR, brp.REVIEW_ROOT)
        brp.REPO_ROOT = self.tmp
        brp.LATEST_RUN_PATH = os.path.join(self.data_dir, "latest_run.json")
        brp.CARDS_DIR = os.path.join(self.data_dir, "cards")
        brp.REVIEW_ROOT = os.path.join(self.data_dir, "review")
        os.makedirs(brp.CARDS_DIR, exist_ok=True)
        self._orig_run_id_env = os.environ.get("GITHUB_RUN_ID")

    def tearDown(self):
        brp.REPO_ROOT, brp.LATEST_RUN_PATH, brp.CARDS_DIR, brp.REVIEW_ROOT = self._orig
        if self._orig_run_id_env is None:
            os.environ.pop("GITHUB_RUN_ID", None)
        else:
            os.environ["GITHUB_RUN_ID"] = self._orig_run_id_env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_run(self, run_id, run_date="2026-10-11"):
        with open(brp.LATEST_RUN_PATH, "w") as f:
            json.dump({
                "run_id": run_id, "run_date": run_date, "run_ts": "x", "status": "NO_VALUE",
                "pick": {"has_pick": False, "reasoning": "nothing today"},
            }, f)

    def test_mismatched_run_id_in_ci_is_refused(self):
        os.environ["GITHUB_RUN_ID"] = "555000"  # this job's actual run
        self._write_run(run_id="444999")          # leftover from a different run
        with self.assertRaises(brp.StaleRunDataError):
            brp.main()

    def test_matching_run_id_in_ci_proceeds(self):
        os.environ["GITHUB_RUN_ID"] = "555000"
        self._write_run(run_id="555000")
        brp.main()  # must not raise

    def test_missing_run_id_field_is_a_warning_not_a_refusal(self):
        # Pre-fix latest_run.json shape -- no run_id key at all. Must not
        # break ingesting data written before this fix landed.
        os.environ["GITHUB_RUN_ID"] = "555000"
        with open(brp.LATEST_RUN_PATH, "w") as f:
            json.dump({"run_date": "2026-10-11", "run_ts": "x", "pick": {"has_pick": False, "reasoning": "x"}}, f)
        brp.main()  # must not raise

    def test_local_dev_without_github_run_id_is_not_checked(self):
        os.environ.pop("GITHUB_RUN_ID", None)
        self._write_run(run_id="local-abc123")
        brp.main()  # must not raise -- no CI run_id to compare against


if __name__ == "__main__":
    unittest.main()
