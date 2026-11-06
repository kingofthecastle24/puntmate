"""Frozen daily results roundup, never a per-result post.
Prepare creates no review/approval. Send uses exact reviewed pixels and captions.
The review receipt is audit evidence, never owner publishing authority.
"""
import argparse,hashlib,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from public_delivery import eligible,load,save,deliver,ROOT,LEDGER,STATE,FOOTER
NZ=ZoneInfo('Pacific/Auckland')
DESTINATIONS=['telegram','instagram_story']
CHECKS=['current_approved_style','rendered_pixels_inspected','heavy_logo','layout_and_no_clipping','wording_and_facts','all_destination_variants','story_safe_areas','captions_and_all_public_copy']

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def settled_key(p):return 'result:'+p['id']+':'+p['result']
def destinations_complete(item):return all(item.get(d,{}).get('status')=='sent' for d in DESTINATIONS)
def previously_reported(p,cfg,state):
 if p['id'] in cfg.get('historical_result_ids',[]):return True
 if destinations_complete(state.get('items',{}).get(settled_key(p),{})):return True
 for item in state.get('roundups',{}).values():
  if settled_key(p) in item.get('outcomes',[]) and item.get('status')=='sent':return True
 return False

def wtd(picks,day):
 start=day-timedelta(days=day.weekday());cohort=[p for p in picks if start.isoformat()<=p['date_posted']<=day.isoformat()]
 rows=[]
 for lane in ['INVESTOR','PUNTER','GAMBLER','DEGEN']:
  group=[p for p in cohort if p['lane']==lane and p['type']!='MULTI'];w=sum(eligible(p) and p['result']=='WIN' for p in group);l=sum(eligible(p) and p['result']=='LOSS' for p in group)
  rows.append({'label':lane,'wins':w,'losses':l,'rate':f'{100*w/(w+l):.0f}%' if w+l else 'N/A','pending':sum(not eligible(p) for p in group),'void':sum(eligible(p) and p['result']=='VOID' for p in group)})
 group=[p for p in cohort if p['type']=='MULTI'];w=sum(eligible(p) and p['result']=='WIN' for p in group);l=sum(eligible(p) and p['result']=='LOSS' for p in group)
 rows.append({'label':'MULTIS','wins':w,'losses':l,'rate':f'{100*w/(w+l):.0f}%' if w+l else 'N/A','pending':sum(not eligible(p) for p in group),'void':sum(eligible(p) and p['result']=='VOID' for p in group)})
 return start,cohort,rows

def plan(picks,cfg,state,now,kind='daily',preview=False):
 day=now.astimezone(NZ).date();key=f'{kind}:{day.isoformat()}'
 if kind=='daily' and day.weekday()==6:return None
 if kind=='weekly' and day.weekday()!=6 and not preview:raise ValueError('Full weekly recap is Sunday only')
 if key in state.get('roundups',{}):return None # retry frozen package only
 reviewed=set(cfg.get('reviewed_result_ids',[]))
 new=[p for p in picks if eligible(p) and p['id'] in reviewed and not previously_reported(p,cfg,state)]
 if preview:new=[p for p in picks if eligible(p) and p['id'] in reviewed and p['date_posted']==day.isoformat()]
 for p in new:
  partial=state.get('items',{}).get(settled_key(p),{})
  if partial:raise ValueError('Prior per-result delivery incomplete/ambiguous; reconcile live destinations first')
 if kind=='daily' and not new:return None
 start,cohort,rows=wtd(picks,day)
 if kind=='weekly':new=[]
 return {'schema_version':1,'id':key,'kind':kind,'date':day.isoformat(),'week_start':start.isoformat(),'as_of':now.isoformat(),'preview_only':preview,'destinations':DESTINATIONS,'outcomes':[settled_key(p) for p in new],'daily':[{k:p.get(k) for k in ['id','selection','match','market','approx_odds','result','lane','type','notes','outcome_source','outcome_checked_at']} for p in new],'record':rows,'pending':[{'selection':p['selection'],'type':p['type'],'label':p.get('pending_label','Result not yet verified')} for p in cohort if not eligible(p)],'cohort_basis':'Picks published in the current NZ Monday-Sunday week; strike rate excludes pending, unverified and void. Whole multis count once, separately.'}

def captions(p):
 day=datetime.fromisoformat(p['date']).strftime('%-d %b %Y');start=datetime.fromisoformat(p['week_start']).strftime('%-d %b')
 text=[('Daily results - '+day) if p['kind']=='daily' else ('Week in review - '+day)]
 if p['preview_only']:text.insert(0,'DESIGN PREVIEW ONLY - NOT FOR PUBLICATION')
 if p['kind']=='daily':
  for x in p['daily']:text.append(x['selection']+' - '+x['result']+'. '+x['notes'])
 text.append(f'Publication week {start} to {day}')
 for x in p['record']:text.append(f"{x['label']}: {x['wins']}W - {x['losses']}L | {x['rate']} | {x['pending']} pending/unverified"+(f" | {x['void']} void" if x['void'] else ''))
 for x in p['pending']:text.append(x['selection']+': '+x['label'])
 text.extend([p['cohort_basis'],FOOTER]);return '\n'.join(text)

def freeze(payload,directory):
 from render_roundup import render_roundup
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
 save(directory/'payload.json',payload);(directory/'caption.txt').write_text(captions(payload)+'\n')
 render_roundup(payload,directory)
 files={p.name:sha(p) for p in directory.iterdir() if p.is_file()}
 manifest={'id':payload['id'],'files':files,'frames':sorted(files.keys() & {p.name for p in directory.glob('frame-*.png')}),'destinations':DESTINATIONS,'preview_only':payload['preview_only']}
 save(directory/'manifest.json',manifest);return manifest

def verify_frozen(directory):
 directory=Path(directory);m=load(directory/'manifest.json',{})
 if m.get('preview_only'):raise ValueError('Design preview cannot be published')
 if not m.get('frames') or m.get('destinations')!=DESTINATIONS:raise ValueError('Wrong audience/missing frames')
 for name,digest in m['files'].items():
  path=(directory/name).resolve()
  if not path.is_relative_to(directory.resolve()) or sha(path)!=digest:raise ValueError('Frozen package changed')
 review=load(directory/'design-review.json',{})
 if review.get('manifest_sha256')!=sha(directory/'manifest.json') or review.get('decision')!='PASS' or not review.get('reviewed_at') or not review.get('reviewer') or not review.get('style_reference') or any(review.get('checks',{}).get(x) is not True for x in CHECKS):raise ValueError('Missing exact final-pixel design review')
 return m,load(directory/'payload.json',{})

def send(directory,now):
 directory=Path(directory);m,p=verify_frozen(directory)
 if len((directory/'caption.txt').read_text())>1024:raise ValueError('Telegram photo caption exceeds1024; shorten and re-review package')
 cfg=load(ROOT/'config/public_delivery.json',{})
 if not cfg.get('results_enabled' if p['kind']=='daily' else 'recap_enabled'):raise ValueError('Publishing paused')
 if cfg.get('first_roundup_requires_owner_proof_review',True):raise ValueError('First roundup owner proof approval not recorded; hold')
 if now.astimezone(NZ).date().isoformat()!=p['date']:raise ValueError('Frozen day expired - prepare and review current package')
 if (now-datetime.fromisoformat(p['as_of'])).total_seconds()>7200:raise ValueError('Record/evidence freshness review required after2h')
 from design_review_gate import verify as verify_run
 import os
 verify_run(ROOT,os.environ.get('GITHUB_RUN_ID',''),os.environ.get('GITHUB_JOB',''))
 picks=load(LEDGER,{'picks':[]})['picks'];start,cohort,record=wtd(picks,now.astimezone(NZ).date())
 if record!=p['record']:raise ValueError('Week-to-date changed since frozen review')
 bykey={settled_key(x):x for x in picks if eligible(x)}
 for x in p['daily']:
  current=bykey.get('result:'+x['id']+':'+x['result'])
  if not current or x['id'] not in cfg.get('reviewed_result_ids',[]):raise ValueError('Market/outcome review missing or changed')
  if any(current.get(k)!=v for k,v in x.items()):raise ValueError('Daily outcome/evidence changed since frozen review')
 state=load(STATE,{'items':{}});roundups=state.setdefault('roundups',{});prior=roundups.get(p['id'])
 if prior and prior.get('manifest_sha256')!=sha(directory/'manifest.json'):raise ValueError('Another package owns this daily slot')
 if prior and prior.get('status')=='sent':return
 if not prior:
  picks=load(LEDGER,{'picks':[]})['picks'];current=plan(picks,cfg,state,now,p['kind'])
  if current is None:raise ValueError('No new results/current slot unavailable')
  bykey={settled_key(x):x for x in picks if eligible(x)}
  for x in p['outcomes']:
   if x not in bykey or previously_reported(bykey[x],cfg,state):raise ValueError('Outcome changed or already reported')
  if current['outcomes']!=p['outcomes']:raise ValueError('New outcomes changed; prepare/review complete roundup again')
  roundups[p['id']]={'status':'attempting','outcomes':p['outcomes'],'manifest_sha256':sha(directory/'manifest.json'),'at':now.isoformat()};save(STATE,state)
 for index,name in enumerate(m['frames']):
  image=directory/name
  if not image.resolve().is_relative_to(ROOT.resolve()):raise ValueError('Freeze inside repository data before send')
  # Each frame/destination inherits ordinary persisted-intent/receipt dedup.
  deliver(p['id']+':frame:'+str(index+1),image,(directory/'caption.txt').read_text() if index==0 else 'Week-to-date record. '+FOOTER,DESTINATIONS,False)
 state=load(STATE,{});state['roundups'][p['id']]['status']='sent';save(STATE,state)
 import subprocess
 subprocess.run(['git','add',str(STATE)],check=True);subprocess.run(['bash','scripts/git_push_retry.sh','chore: complete reviewed daily roundup [skip ci]'],check=True)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','send']);ap.add_argument('--package',required=True);ap.add_argument('--kind',choices=['daily','weekly'],default='daily');ap.add_argument('--as-of');ap.add_argument('--preview',action='store_true');a=ap.parse_args();now=datetime.fromisoformat(a.as_of) if a.as_of else datetime.now(timezone.utc)
 if now.tzinfo is None:raise ValueError('Timezone required')
 if a.action=='send':
  if a.as_of or a.preview:raise ValueError('No simulated time/preview for live send')
  send(a.package,now);return
 cfg=load(ROOT/'config/public_delivery.json',{});p=plan(load(LEDGER,{'picks':[]})['picks'],cfg,load(STATE,{}),now,a.kind,a.preview)
 if p is None:print('No roundup: no new reviewed results, Sunday daily suppression, or existing daily slot.');return
 freeze(p,a.package);print('Frozen review package:',a.package,'No sends or review approval created.')
if __name__=='__main__':main()
