"""Truthful, run-bound prepare diagnostics. Never a publication artifact."""
import json
import os
from pathlib import Path
import run_status


def report(data, expected_run_id, job_status):
    fresh = bool(data and str(data.get('run_id')) == str(expected_run_id))
    if not fresh:
        return {'run_id': expected_run_id, 'state': 'FAILED', 'status': 'MISSING_CURRENT_RUN',
                'reason': 'No current-run prepare record. Inspect the failed job logs.',
                'review_allowed': False}
    status = data.get('status', '')
    failed = job_status != 'success' or status in run_status.OPERATIONAL_FAILURE_STATUSES
    return {'run_id': expected_run_id, 'state': 'FAILED' if failed else 'COMPLETE',
            'status': status, 'reason': data.get('pick', {}).get('reasoning', ''),
            'review_allowed': not failed and bool(data.get('pick', {}).get('has_pick') or data.get('watchlist'))}


def summary(result):
    if result['state'] == 'FAILED':
        return ('## PuntMate prepare FAILED\n\nOperational failure, not an editorial NO_BET. '
                'No approval or publication is allowed from this run.\n\n'
                f"Status: {result['status']}\n\n{result['reason']}\n")
    if result['status'] == run_status.PICK_READY:
        return '## PuntMate prepare complete\n\nPick prepared. Inspect the frozen review package before approval.\n'
    return f"## PuntMate prepare complete\n\nEditorial status: {result['status']}\n\n{result['reason']}\n"


def main():
    root = Path(__file__).resolve().parent.parent
    data_path = root / 'data/latest_run.json'
    try:
        data = json.loads(data_path.read_text())
    except (OSError, ValueError):
        data = None
    result = report(data, os.environ.get('GITHUB_RUN_ID', 'local'), os.environ.get('PREPARE_JOB_STATUS', 'failure'))
    out = root / 'data/diagnostics' / str(result['run_id'])
    out.mkdir(parents=True, exist_ok=True)
    (out / 'prepare-status.json').write_text(json.dumps(result, indent=2))
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
        f.write(summary(result))


if __name__ == '__main__':
    main()
