"""Fail-closed rendered-design review gate. Never creates a pass record.
A receipt is an operator audit, not user publishing authority.
Run --snapshot after final rendering, inspect the actual outgoing pixels, then
record the exact snapshot/run/job and destination checks. Any data change
invalidates the receipt. Existing consent/market/copy/dedup gates still apply.
"""
import hashlib,json,os,sys
from pathlib import Path

CHECKS=("current_approved_style","rendered_pixels_inspected","heavy_logo","layout_and_no_clipping","wording_and_facts","all_destination_variants","story_safe_areas","captions_and_all_public_copy","carousel_direction_and_destination")

def snapshot(root):
    h=hashlib.sha256()
    for p in sorted((root/"data").rglob("*")):
        if not p.is_file() or "design_reviews" in p.parts: continue
        h.update(str(p.relative_to(root)).encode()+b"\0")
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()

def verify(root,run,job):
    path=root/"data/design_reviews"/(run+"-"+job+".json")
    if not path.is_file(): raise ValueError("missing per-run final-pixel review receipt")
    r=json.loads(path.read_text())
    if r.get("run_id")!=run or r.get("job")!=job: raise ValueError("wrong run/job")
    if r.get("snapshot_sha256")!=snapshot(root): raise ValueError("final files changed since review")
    if r.get("decision")!="PASS" or not r.get("reviewer") or not r.get("reviewed_at"): raise ValueError("no completed PASS review")
    if not r.get("style_reference") or not r.get("outgoing_assets") or not r.get("destinations"): raise ValueError("missing exact reference, assets or audiences")
    if any(r.get("checks",{}).get(k) is not True for k in CHECKS): raise ValueError("incomplete design checklist")
    for name,digest in r["outgoing_assets"].items():
        p=(root/name).resolve()
        if not p.is_relative_to(root.resolve()) or not p.is_file(): raise ValueError("missing outgoing asset")
        if hashlib.sha256(p.read_bytes()).hexdigest()!=digest: raise ValueError("outgoing asset changed")
    return r

if __name__=="__main__":
    root=Path(__file__).resolve().parents[1]
    if "--snapshot" in sys.argv: print(snapshot(root));sys.exit(0)
    try: verify(root,os.environ.get("GITHUB_RUN_ID",""),os.environ.get("GITHUB_JOB",""))
    except (ValueError,OSError,KeyError,TypeError) as e: raise SystemExit("DESIGN REVIEW HOLD: "+str(e)+". Inspect final rendered pixels against CURRENT approved style; never auto-stamp a pass.")
    print("Design review receipt matches final bytes; other publishing permissions still apply.")
