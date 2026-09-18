"""Disk persistence for LEAN backtest jobs so restarts keep completed runs."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .models import LeanJobRecord

logger = logging.getLogger("app.lean.job_store")

_STORE_DIR = Path(__file__).resolve().parent / "job_data"


def _path(job_id: str) -> Path:
    safe = "".join(ch for ch in job_id if ch.isalnum() or ch in {"-", "_"})
    return _STORE_DIR / f"{safe}.json"


def save_job(job: LeanJobRecord) -> None:
    try:
        _STORE_DIR.mkdir(parents=True, exist_ok=True)
        payload = job.model_dump(mode="json", by_alias=True)
        _path(job.job_id).write_text(json.dumps(payload, default=str), encoding="utf-8")
    except Exception:
        logger.exception("LEAN_JOB_PERSIST_FAILED | job_id=%s", job.job_id)


def load_job(job_id: str) -> LeanJobRecord | None:
    path = _path(job_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return LeanJobRecord.model_validate(data)
    except Exception:
        logger.exception("LEAN_JOB_LOAD_FAILED | job_id=%s", job_id)
        return None


def load_all() -> dict[str, LeanJobRecord]:
    out: dict[str, LeanJobRecord] = {}
    if not _STORE_DIR.is_dir():
        return out
    for path in _STORE_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            job = LeanJobRecord.model_validate(data)
            out[job.job_id] = job
        except Exception:
            logger.warning("LEAN_JOB_SKIP_BAD_FILE | path=%s", path)
    return out
