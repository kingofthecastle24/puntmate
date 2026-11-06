"""Strict source-backed H2H settlement for canonical public ledger.
No fuzzy team match, no ambiguous date match, no unsupported totals/multis guess.
Unsupported/past-score-window selections remain pending for researched settlement.
"""
import json,os
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'data/results/picks_ledger.json'
def settle(row,games):
 if row['result']!='PENDING' or row['type']=='MULTI' or row.get('market') not in ('Head to Head','Match Winner','Moneyline','Match winner'):return None
 if not row.get('home_team') or not row.get('away_team'):return None
 candidates=[]
 for g in games:
  if not g.get('completed') or g.get('home_team')!=row['home_team'] or g.get('away_team')!=row['away_team']:continue
  when=datetime.fromisoformat(g['commence_time'].replace('Z','+00:00')).astimezone(ZoneInfo('Pacific/Auckland')).date().isoformat()
  if when!=row['date_posted']:continue
  scores={v['name']:v['score'] for v in g.get('scores') or []}
  if row['home_team'] not in scores or row['away_team'] not in scores:continue
  h,a=float(scores[row['home_team']]),float(scores[row['away_team']])
  if h==a:continue # H2H tie rules unresolved, never assume VOID/loss.
  if row['selection'].casefold() not in (row['home_team'].casefold(),row['away_team'].casefold()):continue
  winner=row['home_team'] if h>a else row['away_team']
  candidates.append(('WIN' if winner.casefold()==row['selection'].casefold() else 'LOSS',g))
 return candidates[0] if len(candidates)==1 else None

def main():
 d=json.loads(PATH.read_text());token=os.environ.get('ODDS_API_KEY')
 if not token:raise SystemExit('No scores key; canonical ledger remains unchanged')
 cache={}
 for row in d['picks']:
  if row['result']!='PENDING' or row['type']=='MULTI' or not row.get('sport'):continue
  sport=row['sport'];url='https://api.the-odds-api.com/v4/sports/'+sport+'/scores'
  if sport not in cache:
   r=requests.get(url,params={'apiKey':token,'daysFrom':3},timeout=30);r.raise_for_status();cache[sport]=r.json()
  found=settle(row,cache[sport])
  if not found:continue
  result,game=found;stamp=datetime.now(timezone.utc).isoformat();evidence=ROOT/'data/results/evidence'/(row['id']+'.json');evidence.parent.mkdir(parents=True,exist_ok=True)
  evidence.write_text(json.dumps({'source':url,'checked_at':stamp,'game':game},indent=2)+'\n')
  row.update(result=result,outcome_source=url,outcome_checked_at=stamp,outcome_evidence=str(evidence.relative_to(ROOT)),notes=f"{game['home_team']} {next(v['score'] for v in game['scores'] if v['name']==game['home_team'])} - {game['away_team']} {next(v['score'] for v in game['scores'] if v['name']==game['away_team'])}.")
 PATH.write_text(json.dumps(d,indent=2)+'\n')
if __name__=='__main__':main()
