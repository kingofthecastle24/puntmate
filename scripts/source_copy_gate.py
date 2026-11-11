"""Fail-closed per-pick factual and market review. Never writes approval."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse


def digest(metadata,telegram,instagram):
    return hashlib.sha256(json.dumps([metadata,telegram,instagram],sort_keys=True).encode()).hexdigest()


def _recent(value,max_age,now):
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None or not 0 <= (now-dt).total_seconds() <= max_age:
        raise ValueError('missing, future or stale evidence timestamp')


def verify(review_dir,metadata,telegram,instagram,now=None):
    if not metadata.get('has_pick'):
        return
    now=now or datetime.now(timezone.utc)
    r=json.loads((Path(review_dir)/'source-copy-review.json').read_text())
    if r.get('decision')!='PASS' or not r.get('reviewer'):
        raise ValueError('missing independent source-copy review')
    if r.get('copy_sha256')!=digest(metadata,telegram,instagram):
        raise ValueError('frozen copy changed since factual review')
    _recent(r.get('checked_at',''),3600,now)
    if r.get('all_public_claims_covered') is not True or r.get('no_unvalidated_probability_or_value_claims') is not True:
        raise ValueError('claims or probability assertions remain unchecked')
    claims=r.get('claims',[])
    if not claims or not any(x.get('source_type')=='owning_source' for x in claims):
        raise ValueError('owning fixture/team evidence required')
    for c in claims:
        if not c.get('claim') or not c.get('evidence') or urlparse(c.get('url','')).scheme!='https':
            raise ValueError('each claim needs source URL and inspected supporting evidence')
        _recent(c.get('checked_at',''),86400,now)
    m=r.get('market',{})
    if m.get('source_type')!='bookmaker' or urlparse(m.get('url','')).scheme!='https':
        raise ValueError('actual bookmaker market verification required, not aggregator')
    if any(m.get(k)!=metadata.get(k) for k in ('selection','market','odds')):
        raise ValueError('reviewed bookmaker selection/market/price differ from frozen metadata')
    if not m.get('evidence'):
        raise ValueError('missing inspected market evidence')
    _recent(m.get('checked_at',''),900,now)
