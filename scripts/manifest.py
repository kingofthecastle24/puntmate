"""
manifest.py — SHA-256 checksum helpers for the freeze-before-approval model.

Once a post is drafted, every final file that will be published (Telegram
text, Instagram caption, each PNG) gets hashed into data/review/<pick_id>/manifest.json.
The publish job re-hashes those same files right before posting and refuses
to publish if anything doesn't match — this is what "nothing may be
regenerated after approval" actually enforces in code, not just in policy.
"""

import hashlib
import json
import os


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(base_dir, relative_paths, extra=None):
    """relative_paths: list of paths relative to base_dir that must exist and
    get checksummed. Returns a manifest dict (not yet written to disk)."""
    files = {}
    for rel in relative_paths:
        full = os.path.join(base_dir, rel)
        if not os.path.exists(full):
            raise FileNotFoundError(f"manifest: expected final asset missing: {rel}")
        files[rel] = {
            "sha256": sha256_file(full),
            "bytes": os.path.getsize(full),
        }
    manifest = {"files": files}
    if extra:
        manifest.update(extra)
    return manifest


def verify_manifest(manifest, base_dir):
    """Returns (ok: bool, mismatches: list[str])."""
    mismatches = []
    for rel, meta in manifest.get("files", {}).items():
        full = os.path.join(base_dir, rel)
        if not os.path.exists(full):
            mismatches.append(f"{rel}: file missing at publish time")
            continue
        actual = sha256_file(full)
        if actual != meta.get("sha256"):
            mismatches.append(f"{rel}: checksum mismatch (expected {meta.get('sha256')[:12]}…, got {actual[:12]}…)")
    return (len(mismatches) == 0), mismatches


def write_manifest(manifest, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)


def load_manifest(path):
    with open(path) as f:
        return json.load(f)
