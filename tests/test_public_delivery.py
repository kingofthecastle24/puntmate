import unittest,sys,json,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import public_delivery as mod
class PublicDeliveryTests(unittest.TestCase):
 def test_unverified_not_eligible(self):
  self.assertFalse(mod.eligible({'result':'WIN'}))
 def test_baseline_never_backfilled(self):
  p={'id':'old','result':'LOSS','outcome_source':'https://example.com','outcome_checked_at':'2026-11-06T00:00:00Z','publication_receipt':'receipt.json'}
  self.assertEqual(mod.result_jobs([p],['old']),[])
  self.assertEqual(len(mod.result_jobs([p],[])),1)
 def test_pending_not_eligible(self):
  self.assertFalse(mod.eligible({'result':'PENDING','outcome_source':'https://example.com','outcome_checked_at':'now','publication_receipt':'receipt.json'}))
 def test_dry_run_never_writes_state_or_sends(self):
  with tempfile.TemporaryDirectory() as d,patch.object(mod,'STATE',Path(d)/'state.json'),patch.object(mod.requests,'post') as send:
   mod.deliver('test',Path(d)/'image.png','Result WIN. R18. Gamble responsibly.',['telegram'],True)
   send.assert_not_called();self.assertFalse(mod.STATE.exists())
 def test_ambiguous_attempt_is_held(self):
  with tempfile.TemporaryDirectory() as d,patch.object(mod,'STATE',Path(d)/'state.json'):
   mod.save(mod.STATE,{'items':{'test':{'telegram':{'status':'attempting'}}}})
   with self.assertRaises(RuntimeError):mod.deliver('test',Path(d)/'image.png','Result WIN. R18. Gamble responsibly.',['telegram'],False)
if __name__=='__main__':unittest.main()

class SettlementTests(unittest.TestCase):
 def fixture(self):
  return {'date_posted':'2026-11-06','result':'PENDING','type':'INVESTOR','market':'Head to Head','home_team':'A','away_team':'B','selection':'A'}
 def game(self):
  return {'completed':True,'home_team':'A','away_team':'B','commence_time':'2026-11-06T02:00:00Z','scores':[{'name':'A','score':'3'},{'name':'B','score':'2'}]}
 def test_exact_score_settles(self):
  from settle_public_ledger import settle
  self.assertEqual(settle(self.fixture(),[self.game()])[0],'WIN')
 def test_ambiguous_games_hold(self):
  from settle_public_ledger import settle
  self.assertIsNone(settle(self.fixture(),[self.game(),self.game()]))
 def test_wrong_day_holds(self):
  from settle_public_ledger import settle
  g=self.game();g['commence_time']='2026-11-01T02:00:00Z';self.assertIsNone(settle(self.fixture(),[g]))
 def test_no_multi_guess(self):
  from settle_public_ledger import settle
  p=self.fixture();p['type']='MULTI';self.assertIsNone(settle(p,[self.game()]))
 def test_no_fuzzy_match(self):
  from settle_public_ledger import settle
  g=self.game();g['home_team']='AA';self.assertIsNone(settle(self.fixture(),[g]))

class LedgerAuditTests(unittest.TestCase):
 def test_current_week_receipts(self):
  d=json.loads((mod.ROOT/'data/results/picks_ledger.json').read_text());rows=[p for p in d['picks'] if '2026-11-02'<=p['date_posted']<='2026-11-08']
  self.assertEqual(len(rows),3);self.assertEqual(sum(p['result']=='WIN' for p in rows),1);self.assertEqual(sum(p['result']=='PENDING' for p in rows),2)
  self.assertEqual(len(set(p['id'] for p in rows)),3)
  self.assertEqual({p.get('pending_label') for p in rows if p['result']=='PENDING'},{'Result not yet verified','Not yet played'})
 def test_historical_results_are_baselined(self):
  cfg=mod.load(mod.ROOT/'config/public_delivery.json',{});rows=mod.load(mod.LEDGER,{})['picks']
  self.assertEqual(mod.result_jobs([p for p in rows if p['date_posted']<'2026-11-06'],cfg['historical_result_ids']),[])
 def test_no_private_stakes(self):
  for p in mod.load(mod.LEDGER,{})['picks']:
   self.assertNotIn('stake',p);self.assertNotIn('profit_loss',p)
