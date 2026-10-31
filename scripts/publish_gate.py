"""Publish gate for publish-multi: asset integrity + review hold + attestation.

What this gate guarantees:
1. INTEGRITY - the renderer code/templates/fonts on the publishing ref match
   the approved pin in data/state/approved_renderer.json, and (via the
   existing manifest verification in the workflow) the uploaded asset bytes
   match the frozen package manifest.
2. REVIEW HOLD - publishing is held while any open PR touches the renderer
   paths (scripts/render_brand_templates.py, brand/Templates/, fonts/), so a
   visual change under review can't race a publish either way.
3. ATTESTATION - a deliberate, non-empty attestation reference must be
   supplied at dispatch; it is recorded as SHA-256 hashes binding the
   reference, pick, exact package bytes, action and platforms.

What it does NOT do: it cannot verify that a human approved anything. The
attestation is an audit record of an operator's claim, not proof of approval.
Authorization stays in the conversation record, outside this public repo.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

PIN_PATH = "data/state/approved_renderer.json"
RENDERER_FILES = ["scripts/render_brand_templates.py"]
RENDERER_DIRS = ["brand/Templates", "fonts"]
RENDERER_PATH_PREFIXES = tuple(RENDERER_FILES) + tuple(d + "/" for d in RENDERER_DIRS)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_renderer_fingerprint(repo_root) -> str:
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


def _fail(msg):
    raise SystemExit("PUBLISH GATE: " + msg)


def assert_pin_matches(repo_root):
    """The renderer on the ref being published from must equal the approved
    pin. Fails closed on any drift (unbumped template change, publish from a
    branch with an unreviewed renderer)."""
    actual = compute_renderer_fingerprint(repo_root)
    pin = load_pin(repo_root)
    if actual != pin:
        _fail("renderer on this ref does not match the approved pin - "
              "merge the pin bump for the current renderer before publishing")
    return actual


def renderer_paths_touched(file_paths):
    """True if any changed path is a renderer input."""
    return [p for p in file_paths if p.startswith(RENDERER_PATH_PREFIXES)]


def record_attestation(pick_id, package_dir, action, platforms, attestation_ref):
    """Record a hash-only attestation bound to the exact package bytes,
    action and audience. The reference itself is never stored."""
    if not (attestation_ref or "").strip():
        _fail("no attestation reference supplied - a deliberate dispatch "
              "input is required for publish-multi")
    pkg = Path(package_dir)
    manifest_path = pkg / "manifest.json"
    if not manifest_path.is_file():
        _fail(f"package manifest missing for {pick_id}")
    manifest_sha = _sha256_bytes(manifest_path.read_bytes())
    scope = "|".join([attestation_ref.strip(), pick_id, manifest_sha,
                      action, ",".join(platforms)])
    return {
        "type": "operator_attestation",
        "pick_id": pick_id,
        "action": action,
        "platforms": platforms,
        "package_manifest_sha256": manifest_sha,
        "attestation_ref_sha256": _sha256_bytes(attestation_ref.strip().encode()),
        "artifact_sha256": _sha256_bytes(scope.encode()),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "note": "Audit record only - this attests that a deliberate reference "
                "was supplied at dispatch; it does not verify any approval. "
                "Hashes only, no private text.",
    }


def write_attestation_record(repo_root, record):
    out = Path(repo_root) / "data/approvals" / (record["pick_id"] + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n")
    return str(out)
