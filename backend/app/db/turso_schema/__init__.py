"""Idempotent Turso schema loaders (v1: daily_ohlcv + index_ohlcv)."""
from __future__ import annotations

from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent
V1_SCHEMA_FILE = SCHEMA_DIR / "001_v1_daily_index_ohlcv.sql"
V1_TABLES = ("daily_ohlcv", "index_ohlcv")
FORBIDDEN_V1_TABLES = ("historical_candles", "market_data.candles")


def load_v1_schema_sql() -> str:
    return V1_SCHEMA_FILE.read_text(encoding="utf-8")


def split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    buf: list[str] = []
    for raw_line in sql.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("--"):
            continue
        buf.append(raw_line)
        if line.endswith(";"):
            stmt = "\n".join(buf).strip().rstrip(";").strip()
            buf = []
            if stmt:
                statements.append(stmt)
    tail = "\n".join(buf).strip().rstrip(";").strip()
    if tail:
        statements.append(tail)
    return statements
