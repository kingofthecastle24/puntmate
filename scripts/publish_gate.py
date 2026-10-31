"""Publish gate: binds publishing to the reviewed renderer and a recorded,
privacy-safe approval artifact.

The renderer fingerprint pins the EXACT renderer code + templates + fonts that
produced a package. The approved fingerprint lives in
data/state/approved_renderer.json on main and only changes via a merged PR.
A package rendered by anything else (stale, unmerged, or hand-built assets)
fails closed at publish time.

The approval artifact proves a deliberate, per-publish approval action was
taken and binds it to the exact assets, audience and action - without
committing any private evidence (message IDs, times, channels) to this
public repo. Only SHA-256 hashes are recorded.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

PIN_PATH = "data/state/approved_renderer.json"
RENDERER_FILES = ["scripts/render_brand_templates.py"]
RENDERER_DIRS = ["brand/Templates", "fonts"]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_renderer_fingerprint(repo_root) -> str:
    """SHA-256 over the renderer script, every template in brand/Templates,
    and every font in fonts/. Any change to reviewed visual output changes
    this fingerprint."""
    root = Path(repo_root)
    h = hashlib.sha256()
    files = [root / f for f in RENDERER_FILES]
    for d in RENDERER_DIRS:
        dd = root / d
        assert dd.is_dir(), f"missing renderer input dir: {d}"
        files.extend(sorted(p for p in dd.iterdir() if p.is_file()))
    for f in files:
        assert f.is_file(), f"missing renderer input: {f}"
        h.update(str(f.relative_to(root)).encode())
        h.update(_sha256_bytes(f.read_bytes()).encode())
    return h.hexdigest()


def load_pin(repo_root) -> str:
    p = Path(repo_root) / PIN_PATH
    assert p.is_file(), "approved renderer pin missing - publishing is blocked"
    pin = json.loads(p.read_text())
    fp = pin.get("renderer_fingerprint", "")
    assert len(fp) == 64, "approved renderer pin is empty or malformed"
    return fp


def stamp_manifest(manifest_path, repo_root) -> str:
    """Prepare-side: record which renderer produced this package."""
    fp = compute_renderer_fingerprint(repo_root)
    mp = Path(manifest_path)
    m = json.loads(mp.read_text())
    m["renderer_fingerprint"] = fp
    mp.write_text(json.dumps(m, indent=2))
    return fp


def _fail(msg):
    raise SystemExit("PUBLISH GATE: " + msg)


def assert_publish_allowed(pick_id, package_dir, repo_root, approval_ref, action, platforms):
    """Fail closed unless the package was rendered by the approved renderer
    AND a deliberate approval reference was supplied for this publish.
    Returns the privacy-safe approval record (hashes only)."""
    pkg = Path(package_dir)
    manifest_path = pkg / "manifest.json"
    if not manifest_path.is_file():
        _fail(f"package manifest missing for {pick_id}")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    pkg_fp = manifest.get("renderer_fingerprint", "")
    if len(pkg_fp) != 64:
        _fail("package was not stamped with a renderer fingerprint - "
              "re-run prepare with the gated workflow")
    pin_fp = load_pin(repo_root)
    if pkg_fp != pin_fp:
        _fail("package renderer fingerprint does not match the approved pin "
              "(assets rendered by unreviewed/stale templates)")
    if not (approval_ref or "").strip():
        _fail("no approval reference supplied - publishing requires a "
              "deliberate per-publish approval input")
    manifest_sha = _sha256_bytes(manifest_bytes)
    scope = "|".join([approval_ref.strip(), pick_id, manifest_sha,
                      action, ",".join(platforms)])
    record = {
        "pick_id": pick_id,
        "action": action,
        "platforms": platforms,
        "package_manifest_sha256": manifest_sha,
        "renderer_fingerprint": pkg_fp,
        "approval_ref_sha256": _sha256_bytes(approval_ref.strip().encode()),
        "artifact_sha256": _sha256_bytes(scope.encode()),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "note": "Hashes only. The approval evidence itself is private and "
                "never committed to this public repo.",
    }
    return record


def write_approval_record(repo_root, record):
    out = Path(repo_root) / "data/approvals" / (record["pick_id"] + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2))
    return str(out)
