"""Render the actual approved Results template with public-safe substitutions.
Original template is unchanged. Remove private P/L units and best-win block.
Story layout extends approved canvas, retaining its hierarchy and spacing.
"""
import base64,functools,http.server,json,threading,tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from render_brand_templates import render_wrapper_html,wait_for_dc_boot,set_props_and_settle
ROOT=Path(__file__).resolve().parents[1]
def render_record(payload,output):
 with tempfile.TemporaryDirectory() as tmp:
  template=ROOT/'brand/Templates/PuntMate Results.dc.html';render_wrapper_html(str(template),tmp)
  server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(http.server.SimpleHTTPRequestHandler,directory=tmp));threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=__import__('os').environ.get('CHROME_PATH') or None,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':2400,'height':2300},device_scale_factor=1)
    page.goto(f'http://127.0.0.1:{server.server_port}/{template.name}',wait_until='networkidle');wait_for_dc_boot(page)
    set_props_and_settle(page,{'results':payload.get('native_results',''),'period':payload.get('lane',''),'summary':'','handle':'@puntmatenz'})
    page.evaluate('''p=>{
      const slides=[...document.querySelectorAll('div')].filter(x=>x.style.width==='1080px');const card=slides[0];
      card.style.height='1920px';card.style.padding='88px';
      const [head,body,foot]=card.children;
      head.children[0].innerHTML='<img style="width:380px;height:auto" src="'+p.logo+'">';
      if(!p.lane)head.children[1].remove();else head.children[1].textContent=p.lane;
      body.children[0].textContent=p.kicker;
      body.children[1].textContent=p.headline;body.children[1].style.fontSize=p.headline==='LOSS'?'230px':'150px';body.children[1].style.color=p.headline==='LOSS'?'#FF5C5C':'#EAF7EF';
      body.children[2].textContent=p.subline;
      // Replace only the template's financial-stat block with public record facts.
      const stat=foot.children[0];stat.style.flexDirection='column';stat.innerHTML='';
      p.rows.forEach(row=>{const box=document.createElement('div');box.style.cssText='background:#111815;border:1.5px solid #3A4A40;border-radius:22px;padding:25px 30px;font-size:29px;color:#EAF7EF;line-height:1.3';box.textContent=row;stat.appendChild(box)});
      foot.children[2].style.flexDirection='column';foot.children[2].style.gap='18px';foot.children[2].children[1].textContent='R18 · Gamble responsibly · 0800 654 655';
      card.dataset.exportId='public-record';slides[1].remove();
    }''',{**payload,'logo':'data:image/png;base64,'+base64.b64encode((ROOT/'brand/Logo/puntmate-lockup.png').read_bytes()).decode()})
    page.locator('[data-export-id="public-record"]').screenshot(path=str(output))
    browser.close()
  finally:server.shutdown()
if __name__=='__main__':
 import sys
 render_record(json.loads(Path(sys.argv[1]).read_text()),sys.argv[2])
