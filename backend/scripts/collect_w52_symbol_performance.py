"""Replay 18-year daily history and store per-stock Strategy Tester metrics.

Equivalent to: python -m app.cli.w52_performance_cli collect
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.cli.w52_performance_cli import main


if __name__ == "__main__":
    sys.exit(main())
