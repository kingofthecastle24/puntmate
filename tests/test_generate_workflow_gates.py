"""
Guards the exact fix for run #192 (2026-10-11, external audit item 3): the
generate job's outputs stay set to whatever an earlier successful step
produced even when a LATER step in that job fails (e.g. a git push hitting
a real rebase conflict) -- so has_pick/pick_id could read "true" even
though the job's overall result is "failure" and the review artifact that
pick_id names was never uploaded. approve/on_reject/publish (and their
weekend equivalents) must all require needs.<generate job>.result ==
'success' before trusting those outputs. This can't be unit-tested by
calling Python -- it's a GitHub Actions workflow conditional -- so this
pins the exact text of generate.yml instead of re-deriving the logic by
hand on every change.
"""
import os, re, unittest

WORKFLOW_PATH = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "generate.yml")

GATED_JOBS = {
    "approve": "generate",
    "on_reject": "generate",
    "publish": "generate",
    "approve_weekend": "generate_weekend",
    "on_reject_weekend": "generate_weekend",
    "publish_weekend": "generate_weekend",
}


class GenerateWorkflowResultGateTests(unittest.TestCase):
    def setUp(self):
        with open(WORKFLOW_PATH) as f:
            self.text = f.read()

    def _job_block(self, job_name):
        # Grab from "  <job_name>:" up to the next top-level ("  word:") job
        # header, so each job's own `if:` line is isolated.
        pattern = rf"\n  {re.escape(job_name)}:\n(.*?)(?=\n  [A-Za-z_][A-Za-z0-9_]*:\n|\Z)"
        match = re.search(pattern, self.text, re.DOTALL)
        self.assertIsNotNone(match, f"could not locate job block for {job_name!r} in generate.yml")
        return match.group(1)

    def test_every_downstream_job_requires_its_generate_job_to_have_succeeded(self):
        for job_name, generate_job in GATED_JOBS.items():
            block = self._job_block(job_name)
            if_line = next((line for line in block.splitlines() if line.strip().startswith("if:")), None)
            self.assertIsNotNone(if_line, f"{job_name} has no 'if:' condition at all")
            self.assertIn(
                f"needs.{generate_job}.result == 'success'", if_line,
                f"{job_name}'s if-condition doesn't require needs.{generate_job}.result == 'success': {if_line!r}",
            )


if __name__ == "__main__":
    unittest.main()
