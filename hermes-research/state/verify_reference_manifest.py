"""Read-only integrity check for TradingView golden reference files.

Compares current SHA256 hashes against state/reference_manifest.json.

Never writes to tradingview_reference/. Never replaces files.
A mismatch is REFERENCE_CHANGED and requires user confirmation.

Usage (from repository root):

    python hermes-research/state/verify_reference_manifest.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = Path(__file__).resolve().parent / "reference_manifest.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if not MANIFEST_PATH.is_file():
        print("MANIFEST_MISSING")
        print(f"Expected: {MANIFEST_PATH}")
        return 2

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    changed: list[str] = []
    missing: list[str] = []
    extra_notes: list[str] = []
    matched = 0

    expected = list(manifest.get("expected_files_per_strategy") or [])
    for strategy in manifest.get("strategies") or []:
        name = strategy.get("strategy")
        strat_dir = ROOT / "hermes-research" / "tradingview_reference" / str(name)
        if not strat_dir.is_dir():
            missing.append(f"{name}/")
            continue
        present = {p.name for p in strat_dir.iterdir() if p.is_file()}
        for filename in expected:
            if filename not in present:
                missing.append(f"{name}/{filename}")
        hashed = {item["filename"]: item for item in strategy.get("files") or []}
        for filename in sorted(present):
            path = strat_dir / filename
            digest = sha256_file(path)
            size = path.stat().st_size
            recorded = hashed.get(filename)
            if recorded is None:
                extra_notes.append(f"UNTRACKED {name}/{filename} size={size} sha256={digest}")
                changed.append(f"{name}/{filename}")
                continue
            if digest != recorded.get("sha256") or size != recorded.get("size_bytes"):
                print(
                    f"REFERENCE_CHANGED {name}/{filename} "
                    f"recorded_sha256={recorded.get('sha256')} "
                    f"current_sha256={digest} "
                    f"recorded_size={recorded.get('size_bytes')} "
                    f"current_size={size}"
                )
                changed.append(f"{name}/{filename}")
            else:
                matched += 1
                print(f"MATCH {name}/{filename} sha256={digest} size={size}")

    status = "MATCH"
    if missing:
        status = "REFERENCE_MISSING"
    if changed:
        status = "REFERENCE_CHANGED"
    print(f"STATUS {status} matched={matched} changed={len(changed)} missing={len(missing)}")
    for item in missing:
        print(f"MISSING {item}")
    for item in extra_notes:
        print(item)
    if status != "MATCH":
        print("Do not auto-replace golden reference files. User confirmation required.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
