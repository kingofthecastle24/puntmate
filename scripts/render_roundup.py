"""Current Social Story template adaptation. Review required for each package."""
import functools,http.server,threading,tempfile,os
from pathlib import Path
from playwright.sync_api import sync_playwright
from render_brand_templates import render_wrapper_html,wait_for_dc_boot,set_props_and_settle
ROOT=Path(__file__).resolve().parents[1]

def render_roundup(p,out):
 out=Path(out)
 with tempfile.TemporaryDirectory() as tmp:
  template=ROOT/'brand/Templates/PuntMate Social Templates.dc.html';render_wrapper_html(str(template),tmp)
  server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=tmp));threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   with sync_playwright() as pw:
    b=pw.chromium.launch(executable_path=os.environ.get('CHROME_PATH') or None,args=['--no-sandbox'])
    page=b.new_page(viewport={'width':2400,'height':2300},device_scale_factor=1)
    page.goto(f'http://127.0.0.1:{server.server_port}/{template.name}',wait_until='networkidle');wait_for_dc_boot(page)
    set_props_and_settle(page,{'palette':'amber','accent':'#FFBE3D','accentDim':'#6B501B','accentGlow':'#FFBE3D55','laneTag':'','selection':'THE RECORD','market':'WEEK TO DATE','odds':'','handle':'@puntmatenz'})
    page.evaluate('''p=>{const c=document.querySelector('[data-export-id="story"]');c.style.padding='200px 80px 160px';const [h,b,f]=c.children;h.children[0].children[1].style.fontFamily="'DejaVu Sans',sans-serif";h.children[0].children[1].style.fontWeight='700';f.children[2].textContent='R18 · Gamble responsibly · 0800 654 655';b.style.gap='25px';}''',p)
    # Daily outcome frame(s), same hierarchy and amber large mono outcome slot.
    for i,x in enumerate(p['daily']):
     page.evaluate('''p=>{const c=document.querySelector('[data-export-id="story"]'),[h,b,f]=c.children;h.children[1].textContent=p.x.lane;const old=b.querySelector('[data-score]');if(old)old.remove();b.children[0].textContent='// DAILY RESULTS · '+p.date;b.children[1].textContent=p.x.match;b.children[2].textContent=p.x.selection;b.children[2].style.cssText='color:#EAF7EF;font-size:88px;font-weight:700;line-height:1.02;letter-spacing:-2px;max-width:760px';b.children[3].textContent=(p.x.market||'Match winner').toUpperCase()+' · POSTED '+p.x.approx_odds;b.children[4].textContent=p.x.result;const s=document.createElement('div');s.dataset.score='true';s.style.cssText='font-size:34px;color:#8FA69A;line-height:1.4;max-width:900px';s.textContent=p.x.notes;b.appendChild(s);if(p.preview){const v=document.createElement('div');v.textContent='DESIGN PREVIEW · NOT A NEW UPDATE';v.style.cssText="font-size:22px;color:#FFBE3D;font-family:'Space Mono',monospace";b.appendChild(v);}}''',{'x':x,'date':__import__('datetime').date.fromisoformat(p['date']).strftime('%-d %b %Y'),'preview':p['preview_only']})
     page.locator('[data-export-id="story"]').screenshot(path=str(out/f'frame-{i+1:02d}.png'))
    page.evaluate('''p=>{const c=document.querySelector('[data-export-id="story"]'),[h,b,f]=c.children;h.children[1].style.visibility='hidden';b.innerHTML='';function el(text,size,color,font){const x=document.createElement('div');x.style.cssText=`font-size:${size}px;color:${color};font-family:${font||"'Space Grotesk',sans-serif"};line-height:1.22`;x.textContent=text;b.appendChild(x);return x;}el('// WEEK TO DATE',26,'#FFBE3D',"'Space Mono',monospace");el(p.range,64,'#EAF7EF').style.fontWeight='700';el('As of '+p.asof,27,'#8FA69A');const table=document.createElement('div');table.style.cssText='margin-top:24px;display:flex;flex-direction:column;gap:18px';b.appendChild(table);p.record.forEach(r=>{const row=document.createElement('div');row.style.cssText='display:flex;justify-content:space-between;align-items:baseline;gap:14px;padding:16px 0;border-bottom:1px solid #26352D';const name=document.createElement('span');name.style.cssText="font-size:29px;letter-spacing:2px;font-family:'Space Mono',monospace;color:#FFBE3D";name.textContent=r.label;const n=document.createElement('span');n.style.cssText="font-size:40px;font-weight:700;color:#EAF7EF;font-family:'Space Mono',monospace";n.textContent=r.wins+'W '+r.losses+'L · '+r.rate;row.append(name,n);table.appendChild(row)});const pending=p.record.reduce((a,r)=>a+r.pending,0);el(pending+' pending / not yet played · '+p.record.reduce((a,r)=>a+r.void,0)+' void',28,'#8FA69A');el('Multis count once, separately. Strike rate = wins / (wins + losses).' ,26,'#8FA69A').style.whiteSpace='pre-line';if(p.preview_only)el('DESIGN PREVIEW · NOT A NEW UPDATE',22,'#FFBE3D',"'Space Mono',monospace");}''',{'range':__import__('datetime').date.fromisoformat(p['week_start']).strftime('%-d')+'-'+__import__('datetime').date.fromisoformat(p['date']).strftime('%-d %b %Y'),'asof':__import__('datetime').datetime.fromisoformat(p['as_of']).astimezone(__import__('zoneinfo').ZoneInfo('Pacific/Auckland')).strftime('%-d %b %H:%M NZ'),'record':p['record'],'preview_only':p['preview_only']})
    page.locator('[data-export-id="story"]').screenshot(path=str(out/f'frame-{len(p["daily"])+1:02d}.png'))
    b.close()
  finally:server.shutdown()
