import sys,json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from source_copy_gate import verify,digest
from render_brand_templates import kickoff_display
class ReviewTests(unittest.TestCase):
 def test_dst(self):
  self.assertEqual(kickoff_display('2026-11-07T00:00:00Z')[1],'Sat 7 Nov, 1:00pm NZDT')
  self.assertEqual(kickoff_display('2026-07-18T07:05:00Z')[1],'Sat 18 Jul, 7:05pm NZST')
  self.assertEqual(kickoff_display('2026-11-07T00:00:00'),(None,None))
 def test_missing_receipt_blocks(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(FileNotFoundError): verify(d,{'has_pick':True},'a','b')
 def test_no_bet_has_no_market_requirement(self):
  verify('/missing',{'has_pick':False},'No recommended bet','')
 def test_review_bound_to_copy_and_bookmaker(self):
  now=datetime(2026,11,6,20,0,tzinfo=timezone.utc);t=now.isoformat();m={'has_pick':True,'selection':'HAWKS','market':'Head to Head','odds':'1.35'}
  r={'decision':'PASS','reviewer':'operator','checked_at':t,'copy_sha256':digest(m,'a','b'),'all_public_claims_covered':True,'no_unvalidated_probability_or_value_claims':True,'claims':[{'claim':'fixture','evidence':'fixture inspected','url':'https://nba.com/game/x','source_type':'owning_source','checked_at':t}],'market':{'selection':'HAWKS','market':'Head to Head','odds':'1.35','source_type':'bookmaker','url':'https://bookmaker.example/market','evidence':'actual current market inspected','checked_at':t}}
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'source-copy-review.json';p.write_text(json.dumps(r));verify(d,m,'a','b',now)
   with self.assertRaises(ValueError): verify(d,m,'changed','b',now)
   r['market']['checked_at']='2026-11-06T19:00:00+00:00';p.write_text(json.dumps(r))
   with self.assertRaises(ValueError): verify(d,m,'a','b',now)
   r['market']['checked_at']=t
   r['checked_at']='2026-11-06T18:00:00+00:00';p.write_text(json.dumps(r))
   with self.assertRaises(ValueError): verify(d,m,'a','b',now)
   r['checked_at']=t
   r['market']['source_type']='aggregator';p.write_text(json.dumps(r))
   with self.assertRaises(ValueError): verify(d,m,'a','b',now)
if __name__=='__main__':unittest.main()
