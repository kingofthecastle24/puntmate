import unittest,sys,tempfile,json,hashlib
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import result_roundup as r
class RoundupTests(unittest.TestCase):
 def setUp(self):
  self.now=datetime.fromisoformat('2026-11-07T18:00:00+13:00');self.p={'id':'p','date_posted':'2026-11-06','selection':'A','match':'A vs B','lane':'INVESTOR','type':'INVESTOR','result':'WIN','notes':'A won.','publication_receipt':'receipt','outcome_source':'https://fixture.invalid','outcome_checked_at':'2026-11-07T01:00:00Z'};self.cfg={'reviewed_result_ids':['p']}
 def test_only_new_verified(self):
  self.assertIsNotNone(r.plan([self.p],self.cfg,{},self.now))
  self.assertIsNone(r.plan([self.p],{}, {},self.now))
  self.assertIsNone(r.plan([{**self.p,'outcome_source':''}],self.cfg,{},self.now))
 def test_existing_result_both_destinations_not_repeated(self):
  state={'items':{r.settled_key(self.p):{d:{'status':'sent'} for d in r.DESTINATIONS}}}
  self.assertIsNone(r.plan([self.p],self.cfg,state,self.now))
 def test_partial_legacy_receipt_holds(self):
  with self.assertRaises(ValueError):r.plan([self.p],self.cfg,{'items':{r.settled_key(self.p):{'telegram':{'status':'sent'}}}},self.now)
 def test_baseline_not_repeated(self):self.assertIsNone(r.plan([self.p],{**self.cfg,'historical_result_ids':['p']},{},self.now))
 def test_one_slot_per_day(self):self.assertIsNone(r.plan([self.p],self.cfg,{'roundups':{'daily:2026-11-07':{'status':'attempting'}}},self.now))
 def test_sunday_suppresses_daily(self):self.assertIsNone(r.plan([self.p],self.cfg,{},datetime.fromisoformat('2026-11-08T18:00:00+13:00')))
 def test_weekly_plan_requires_sunday(self):
  with self.assertRaises(ValueError):r.plan([self.p],self.cfg,{},self.now,'weekly')
 def test_whole_multi_and_void_pending_separate(self):
  rows=r.wtd([self.p,{**self.p,'id':'m','type':'MULTI','lane':'GAMBLER','result':'LOSS'},{**self.p,'id':'v','result':'VOID'},{**self.p,'id':'q','result':'PENDING'}],self.now.date())[2]
  self.assertEqual((rows[0]['wins'],rows[0]['losses'],rows[0]['rate'],rows[0]['void'],rows[0]['pending']),(1,0,'100%',1,1));self.assertEqual(rows[-1]['losses'],1);self.assertEqual(rows[2]['losses'],0)
 def test_preview_cannot_publish(self):
  with tempfile.TemporaryDirectory() as d:
   Path(d,'manifest.json').write_text(json.dumps({'preview_only':True}))
   with self.assertRaises(ValueError):r.verify_frozen(d)
 def test_exact_bytes_and_review_required(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'frame-01.png').write_bytes(b'fixture');(p/'payload.json').write_text('{}');m={'frames':['frame-01.png'],'files':{'frame-01.png':r.sha(p/'frame-01.png')},'destinations':r.DESTINATIONS,'preview_only':False};(p/'manifest.json').write_text(json.dumps(m))
   with self.assertRaises(ValueError):r.verify_frozen(p)
   review={'manifest_sha256':r.sha(p/'manifest.json'),'decision':'PASS','reviewed_at':'fixture','reviewer':'fixture','style_reference':'fixture','checks':dict.fromkeys(r.CHECKS,True)};(p/'design-review.json').write_text(json.dumps(review));r.verify_frozen(p)
   (p/'frame-01.png').write_bytes(b'changed')
   with self.assertRaises(ValueError):r.verify_frozen(p)
if __name__=='__main__':unittest.main()
