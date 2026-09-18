"""Compatibility wrapper so `uvicorn main:app` works when run from the `backend/` folder.

This imports the FastAPI `app` created in `backend/app/main.py` (module `backend.app.main`).
"""

import sys
from pathlib import Path

# Ensure repo root is on sys.path so subprocesses spawned by the reloader
# can import the top-level `backend` package even when cwd is `backend/`.
repo_root = Path(__file__).resolve().parents[1]
backend_dir = Path(__file__).resolve().parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

try:
    from backend.app.main import app
except ImportError:
    from app.main import app

__all__ = ["app"]
