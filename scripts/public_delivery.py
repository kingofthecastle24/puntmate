"""Source-backed public results/news delivery. Sends default OFF until proof review.
No private challenge stakes, no historic backfill, no feed/Facebook destinations.
Per-destination receipts survive partial failure; ambiguous sends are held for review.
"""
import argparse, hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
import requests
from copy_validator import validate_text
ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT/'data/results/picks_ledger.json'
STATE = ROOT/'data/state/public_delivery.json'
FOOTER = 'R18 | Gamble responsibly | 0800 654 655'

def load(path, default):
    return json.loads(path.read_text()) if path.exists() else default

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(value, indent=2)+'\n');tmp.replace(path)

def eligible(p):
    return p.get('result') in ('WIN','LOSS','VOID') and p.get('outcome_source','').startswith('https://') and bool(p.get('outcome_checked_at')) and bool(p.get('publication_receipt'))

def render_result(p, output):
    from render_public_record import render_record
    render_record({'lane':p['lane'],'native_results':'', 'kicker':'// THE RESULT · '+p['date_posted'],
        'headline':p['result'],'subline':p['selection'],
        'rows':[p['match'],p.get('market','Match winner')+' | posted odds '+str(p.get('approx_odds','N/A')),p['notes'], 'Whole multi counts once.' if p['type']=='MULTI' else 'Single selection.']}, output)

def render_recap(lines, output):
    from render_public_record import render_record
    render_record({'lane':'','native_results':'','kicker':'// WEEK IN REVIEW',
        'headline':'THE RECORD','subline':lines[0]+' · '+lines[1], 'rows':lines[2:]},output)

def deliver(key, image, caption, destinations, dry=True):
    validate_text(caption, risk='STANDARD_PICK', public=True)
    state=load(STATE,{'items':{}});item=state.setdefault('items',{}).setdefault(key,{})
    for dest in destinations:
        prior=item.get(dest,{})
        if prior.get('status')=='sent':continue
        if prior.get('status')=='attempting':raise RuntimeError(f'{key}/{dest}: previous outcome ambiguous; inspect live source before retry')
        if dry:print('DRY RUN',key,dest,str(image),caption);continue
        item[dest]={'status':'attempting','at':datetime.now(timezone.utc).isoformat()};save(STATE,state)
        import subprocess
        subprocess.run(['git','add',str(STATE)],check=True)
        subprocess.run(['bash','scripts/git_push_retry.sh','chore: delivery intent before send [skip ci]'],check=True)
        if dest=='telegram':
            token=os.environ['TELEGRAM_BOT_TOKEN']; channel=os.environ['TELEGRAM_CHANNEL_ID']
            with image.open('rb') as f:r=requests.post('https://api.telegram.org/bot'+token+'/sendPhoto',data={'chat_id':channel,'caption':caption},files={'photo':f},timeout=60).json()
            if not r.get('ok'):raise RuntimeError('Telegram rejected delivery; inspect state before retry')
            receipt={'message_id':r['result']['message_id']}
        elif dest=='instagram_story':
            import subprocess
            subprocess.run(['git','add',str(image)],check=True)
            subprocess.run(['bash','scripts/git_push_retry.sh','chore: public delivery image [skip ci]'],check=True)
            url='https://raw.githubusercontent.com/'+os.environ['GITHUB_REPOSITORY']+'/main/'+str(image.relative_to(ROOT))
            check=requests.get(url,timeout=30);check.raise_for_status()
            assert hashlib.sha256(check.content).hexdigest()==hashlib.sha256(image.read_bytes()).hexdigest()
            from post_instagram_story import post_story_to_instagram
            mid=post_story_to_instagram(url)
            if not mid:raise RuntimeError('Instagram Story outcome failed/ambiguous; inspect before retry')
            receipt={'media_id':mid}
        else:raise ValueError('Unauthorized destination')
        item[dest]={'status':'sent','receipt':receipt,'at':datetime.now(timezone.utc).isoformat()};save(STATE,state)
        subprocess.run(['git','add',str(STATE)],check=True)
        subprocess.run(['bash','scripts/git_push_retry.sh','chore: delivery receipt after send [skip ci]'],check=True)
    return state

def result_jobs(picks, baseline):
    return [p for p in picks if eligible(p) and p['id'] not in baseline]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['results','recap','news']);ap.add_argument('--send',action='store_true');ap.add_argument('--payload');args=ap.parse_args()
    cfg=load(ROOT/'config/public_delivery.json',{});dry=not args.send
    pl=load(Path(args.payload),{}) if args.payload else {}
    reviewed=args.mode=='recap' and bool(pl.get('reviewed_image') and pl.get('approved_image_sha256') and pl.get('reviewed_caption'))
    if args.send and not reviewed and args.mode in ('results','recap') and cfg.get('result_delivery_mode')=='daily_roundup':
        raise SystemExit('Per-result/legacy recap delivery retired. Use a frozen, reviewed result_roundup package; never bypass the design gate.')
    if args.send and not reviewed and not cfg.get(args.mode+'_enabled'):raise SystemExit('Live delivery held pending proof review')
    picks=load(LEDGER,{'picks':[]})['picks'];out=ROOT/'data/public_delivery';baseline=cfg.get('historical_result_ids',[])
    if args.mode=='results':
        for p in result_jobs(picks,baseline):
            if p['id'] not in cfg.get('reviewed_result_ids',[]):
                print('HELD: exact market grading review required',p['id']);continue
            text=f"{p['selection']} - {p['result']}. {p['notes']}\n{FOOTER}"
            image=out/(p['id']+'.png');render_result(p,image)
            deliver('result:'+p['id']+':'+p['result'],image,text,['telegram','instagram_story'],dry)
    elif args.mode=='recap':
        # Publication cohort is explicit. Never present this as all-time or imply missing rows are losses.
        payload=load(Path(args.payload),{}) if args.payload else {}
        start,end=payload.get('start'),payload.get('end')
        if not start or not end:raise SystemExit('Explicit publication-date start/end required')
        if reviewed:
            img=ROOT/pl['reviewed_image'];assert hashlib.sha256(img.read_bytes()).hexdigest()==pl['approved_image_sha256'],'Image differs from inspected proof'
            deliver('recap:'+start+':'+end,img,pl['reviewed_caption'],['telegram','instagram_story'],dry);return
        cohort=[p for p in picks if start<=p['date_posted']<=end]
        sd=datetime.fromisoformat(start); ed=datetime.fromisoformat(end)
        week_label = (f'{sd.day}-{ed.day} {ed.strftime("%b %Y")}' if sd.month==ed.month else f'{sd.strftime("%d %b")} - {ed.strftime("%d %b %Y")}')
        now_nz=datetime.now(timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo('Pacific/Auckland'))
        lines=[f'Publication week {week_label}', 'As of '+now_nz.strftime('%d %b %Y, ')+now_nz.strftime('%-I:%M%p').lower()+' NZDT']
        def official(p): return p['lane'] in ('INVESTOR','PUNTER') and 'nofficial' not in (p.get('notes','')+' '+p.get('type','')+' '+p.get('lane','')).lower()
        def lane_line(lane, group):
            w=sum(p['result']=='WIN' for p in group);l=sum(p['result']=='LOSS' for p in group)
            base=f'{lane}: {w}W - {l}L'
            return base+(f' | {100*w/(w+l):.0f}%' if w and l else '')
        lines.append('##OFFICIAL RECORD')
        for lane in ['INVESTOR','PUNTER']:
            group=[p for p in cohort if p['lane']==lane and p['type']!='MULTI' and official(p)]
            if group: lines.append(lane_line(lane, group))
        lines.append('##UNOFFICIAL RECORD')
        for lane in ['GAMBLER','DEGEN','INVESTOR','PUNTER']:
            group=[p for p in cohort if p['lane']==lane and p['type']!='MULTI' and not official(p)]
            if group: lines.append(lane_line(lane, group))
        multis=[p for p in cohort if p['type']=='MULTI'];mw=sum(p['result']=='WIN' for p in multis); ml=sum(p['result']=='LOSS' for p in multis)
        if multis: lines.append(f'Multis (unofficial): {mw}W - {ml}L'+(f' | {100*mw/(mw+ml):.0f}%' if mw and ml else ''))
        
        for p in cohort:
            if p['result']=='PENDING':
                lines.append(p['selection']+': '+p.get('pending_label','Result not yet verified'))
        if any(p['result']=='UNRESOLVED' for p in cohort):lines.append('Some results not yet verified')
        image=out/'recap.png';render_recap(lines,image)
        caption_lines=[l[2:] if l.startswith('##') else l for l in lines]
        deliver('recap:'+start+':'+end,image,'\n'.join(caption_lines+[FOOTER]),['telegram','instagram_story'],dry)
    else:
        payload=load(Path(args.payload),{})
        assert payload.get('kind')=='sports_news' and payload.get('destinations')==['instagram_story']
        checked=datetime.fromisoformat(payload['checked_at']);age=(datetime.now(timezone.utc)-checked).total_seconds()
        assert 0<=age<=3600,'News evidence older than one hour; recheck actual sources, never just change timestamp'
        assert payload.get('evidence_urls') and payload.get('approved_image_sha256')
        image=ROOT/payload['image']
        if not image.exists():
            import base64
            image.write_bytes(base64.b64decode(Path(str(image)+'.b64').read_text()))
        assert hashlib.sha256(image.read_bytes()).hexdigest()==payload['approved_image_sha256'],'Image differs from inspected proof'
        deliver('news:'+payload['id'],image,payload['caption'],['instagram_story'],dry)

if __name__=='__main__':main()
