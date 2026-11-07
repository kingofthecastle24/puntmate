import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import main as pipeline
import prepare_report
import run_status
import build_review_package as packages
import send_preview


class FailureTests(unittest.TestCase):
    def test_credit_failure_writes_fresh_model_error_and_still_fails_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'latest.json'
            p.write_text(json.dumps({'run_id': 'old', 'pick': {'has_pick': True}}))
            with patch.object(pipeline, 'LATEST_RUN_PATH', str(p)), patch('fetch_odds.fetch_upcoming_odds', return_value=[{'match': 'A vs B', 'sport': 'test'}]), patch('fetch_news.fetch_news', return_value={}), patch('generate_pick.generate_pick_for_matches', side_effect=RuntimeError('Your credit balance is too low to access the Anthropic API.')), patch.object(pipeline, '_recently_actioned_slugs', return_value=[]), patch.dict(os.environ, {'GITHUB_RUN_ID': 'new'}):
                with self.assertRaises(RuntimeError):
                    pipeline.run()
            d = json.loads(p.read_text())
            self.assertEqual(d['run_id'], 'new')
            self.assertEqual(d['status'], run_status.MODEL_ERROR)
            self.assertEqual(d['failure_code'], 'PROVIDER_CREDIT_BLOCKED')
            self.assertFalse(d['pick']['has_pick'])
            self.assertNotIn('watchlist', d)
            self.assertNotIn('degen_watch', d)
            self.assertEqual(prepare_report.report(d, 'new', 'failure')['state'], 'FAILED')

    def test_returned_model_error_cannot_create_watchlist_or_degen_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'latest.json'
            error = {'has_pick': False, 'status': 'MODEL_ERROR', 'reasoning': 'invalid response'}
            with patch.object(pipeline, 'LATEST_RUN_PATH', str(p)), patch('fetch_odds.fetch_upcoming_odds', return_value=[{'match': 'A vs B', 'sport': 'test'}]), patch('fetch_news.fetch_news', return_value={}), patch('generate_pick.generate_pick_for_matches', return_value=error), patch.object(pipeline, '_recently_actioned_slugs', return_value=[]):
                with self.assertRaises(RuntimeError): pipeline.run()
            d=json.loads(p.read_text())
            self.assertEqual(d['status'],'MODEL_ERROR')
            self.assertNotIn('watchlist',d)

    def test_failed_or_stale_data_never_becomes_no_bet_summary(self):
        for d in [None, {'run_id':'old'}, {'run_id':'new', 'status':'MODEL_ERROR', 'pick':{'reasoning':'provider failed'}}]:
            r = prepare_report.report(d, 'new', 'failure')
            self.assertEqual(r['state'], 'FAILED')
            self.assertFalse(r['review_allowed'])
            self.assertNotIn('No defensible pick', prepare_report.summary(r))

    def test_successful_no_value_remains_editorial(self):
        d = {'run_id':'new', 'status':'NO_VALUE','pick':{'has_pick':False,'reasoning':'Nothing cleared review'}}
        r = prepare_report.report(d,'new','success')
        self.assertEqual(r['state'],'COMPLETE')
        self.assertIn('Editorial status: NO_VALUE',prepare_report.summary(r))

    def test_every_operational_status_blocks_package_even_with_watchlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'latest.json'
            for status in run_status.OPERATIONAL_FAILURE_STATUSES:
                p.write_text(json.dumps({'status':status,'pick':{'has_pick':False},'watchlist':[{'match':'A vs B'}]}))
                with patch.object(packages,'LATEST_RUN_PATH',str(p)),patch.object(packages,'_assert_not_stale'):
                    with self.assertRaisesRegex(RuntimeError,'Operational prepare failure'):
                        packages.main()

    def test_error_metadata_never_transitions_or_emails(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad';p.mkdir();(p/'post-metadata.json').write_text(json.dumps({'status':'MODEL_ERROR'}))
            with patch.object(send_preview,'REVIEW_ROOT',tmp),patch.dict(os.environ,{'PICK_ID':'bad'}),patch.object(send_preview,'_safe_transition') as transition:
                with self.assertRaises(RuntimeError):send_preview.main()
                transition.assert_not_called()

    def test_workflow_diagnostic_not_review_and_preview_not_always(self):
        s=(Path(__file__).resolve().parents[1]/'.github/workflows/generate.yml').read_text()
        self.assertIn('PREPARE_JOB_STATUS: ${{ job.status }}',s)
        self.assertIn('name: puntmate-prepare-status-${{ github.run_id }}',s)
        self.assertNotIn('No defensible pick today (NO_BET)',s)
        block=s.split('- name: Send approval-preview email')[1].split('- name: Commit ledger')[0]
        self.assertIn('if: success()',block)

if __name__=='__main__':unittest.main()
