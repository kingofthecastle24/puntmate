"""Source-backed public results/news delivery. Sends default OFF until proof review.
No private challenge stakes, no historic backfill, no feed/Facebook destinations.
Per-destination receipts survive partial failure; ambiguous sends are held for review.
"""
import argparse, hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
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

def render(title, lines, output):
    img=Image.new('RGB',(1080,1920),'#0b0f0d');d=ImageDraw.Draw(img)
    def font(s,bold=False):return ImageFont.truetype(str(ROOT/'fonts'/('InstrumentSans-Bold.ttf' if bold else 'InstrumentSans-Regular.ttf')),s)
    logo=Image.open(ROOT/'brand/Logo/puntmate-lockup.png').convert('RGBA');logo.thumbnail((470,140));img.paste(logo,(90,110),logo)
    d.text((90,350),title,font=font(68,True),fill='#35e07e')
    y=530
    for text in lines:
        words=str(text).split();line=''
        for word in words:
            trial=(line+' '+word).strip()
            if d.textlength(trial,font=font(40))>890:
                d.text((90,y),line,font=font(40),fill='#eaf7ef');y+=57;line=word
            else:line=trial
        d.text((90,y),line,font=font(40),fill='#eaf7ef');y+=92
    if y>1730:raise ValueError('Card content overflows safe area; split the card before publication')
    d.text((90,1800),'@PUNTMATENZ',font=font(29,True),fill='#eaf7ef')
    d.text((90,1855),FOOTER,font=font(25),fill='#93ac9d')
    output.parent.mkdir(parents=True,exist_ok=True);img.save(output)

def deliver(key, image, caption, destinations, dry=True):
    validate_text(caption, risk='STANDARD_PICK', public=True)
    state=load(STATE,{'items':{}});item=state.setdefault('items',{}).setdefault(key,{})
    for dest in destinations:
        prior=item.get(dest,{})
        if prior.get('status')=='sent':continue
        if prior.get('status')=='attempting':raise RuntimeError(f'{key}/{dest}: previous outcome ambiguous; inspect live source before retry')
        if dry:print('DRY RUN',key,dest,str(image),caption);continue
        item[dest]={'status':'attempting','at':datetime.now(timezone.utc).isoformat()};save(STATE,state)
        if dest=='telegram':
            token=os.environ['TELEGRAM_BOT_TOKEN']; channel=os.environ['TELEGRAM_CHANNEL_ID']
            with image.open('rb') as f:r=requests.post('https://api.telegram.org/bot'+token+'/sendPhoto',data={'chat_id':channel,'caption':caption},files={'photo':f},timeout=60).json()
            if not r.get('ok'):raise RuntimeError('Telegram rejected delivery; inspect state before retry')
            receipt={'message_id':r['result']['message_id']}
        elif dest=='instagram_story':
            from post_instagram_story import upload_to_catbox,post_story_to_instagram
            mid=post_story_to_instagram(upload_to_catbox(str(image)))
            if not mid:raise RuntimeError('Instagram Story outcome failed/ambiguous; inspect before retry')
            receipt={'media_id':mid}
        else:raise ValueError('Unauthorized destination')
        item[dest]={'status':'sent','receipt':receipt,'at':datetime.now(timezone.utc).isoformat()};save(STATE,state)
    return state

def result_jobs(picks, baseline):
    return [p for p in picks if eligible(p) and p['id'] not in baseline]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['results','recap','news']);ap.add_argument('--send',action='store_true');ap.add_argument('--payload');args=ap.parse_args()
    cfg=load(ROOT/'config/public_delivery.json',{});dry=not args.send
    if args.send and not cfg.get(args.mode+'_enabled'):raise SystemExit('Live delivery held pending proof review')
    picks=load(LEDGER,{'picks':[]})['picks'];out=ROOT/'data/public_delivery';baseline=cfg.get('historical_result_ids',[])
    if args.mode=='results':
        for p in result_jobs(picks,baseline):
            text=f"{p['selection']} - {p['result']}. {p['notes']}\n{FOOTER}"
            image=out/(p['id']+'.png');render('THE RESULT',[p['lane'],p['selection'],p['result'],p['notes'],'Whole multi counts once.' if p['type']=='MULTI' else 'Single selection.'],image)
            deliver('result:'+p['id']+':'+p['result'],image,text,['telegram','instagram_story'],dry)
    elif args.mode=='recap':
        # Publication cohort is explicit. Never present this as all-time or imply missing rows are losses.
        payload=load(Path(args.payload),{}) if args.payload else {}
        start,end=payload.get('start'),payload.get('end')
        if not start or not end:raise SystemExit('Explicit publication-date start/end required')
        cohort=[p for p in picks if start<=p['date_posted']<=end]
        lines=[f'Published {start} to {end}']
        for lane in ['INVESTOR','PUNTER','GAMBLER']:
            group=[p for p in cohort if p['lane']==lane and p['type']!='MULTI'];w=sum(p['result']=='WIN' for p in group);l=sum(p['result']=='LOSS' for p in group)
            lines.append(f'{lane} singles: {w}W - {l}L')
        multis=[p for p in cohort if p['type']=='MULTI'];lines.append(f"Multis: {sum(p['result']=='WIN' for p in multis)}W - {sum(p['result']=='LOSS' for p in multis)}L")
        lines.append(f"Pending/unverified: {sum(p['result'] in ('PENDING','UNRESOLVED') for p in cohort)}")
        image=out/'recap.png';render('WEEK IN REVIEW',lines,image)
        deliver('recap:'+start+':'+end,image,'\n'.join(lines+[FOOTER]),['telegram','instagram_story'],dry)
    else:
        payload=load(Path(args.payload),{})
        assert payload.get('kind')=='sports_news' and payload.get('destinations')==['instagram_story']
        checked=datetime.fromisoformat(payload['checked_at']);age=(datetime.now(timezone.utc)-checked).total_seconds()
        assert 0<=age<=3600,'News evidence older than one hour; recheck actual sources, never just change timestamp'
        assert payload.get('evidence_urls') and payload.get('approved_image_sha256')
        image=ROOT/payload['image'];assert hashlib.sha256(image.read_bytes()).hexdigest()==payload['approved_image_sha256'],'Image differs from inspected proof'
        deliver('news:'+payload['id'],image,payload['caption'],['instagram_story'],dry)

if __name__=='__main__':main()
