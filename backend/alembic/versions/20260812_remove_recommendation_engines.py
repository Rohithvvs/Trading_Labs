"""Remove Production / RE-001 / RE-002 Recommendation Engines.

Drops the lab engine decision table (``recommendation_engine_decisions``) and
all engine-attribution columns from the paper trading tables
(``source_engine_id``, ``source_engine_version``, ``source_recommendation_id``,
``experiment_id``) together with their indexes.

The open-position uniqueness index is recreated without the engine dimension
(position uniqueness is now ``(account_id, symbol)``).

Revision ID: 20260812_remove_recommendation_engines
Revises: 4077a451eb8f
Create Date: 2026-08-12
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260812_remove_recommendation_engines"
down_revision: Union[str, Sequence[str], None] = "4077a451eb8f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENGINE_COLUMNS = (
    "source_engine_id",
    "source_engine_version",
    "source_recommendation_id",
    "experiment_id",
)

_PAPER_TABLES = (
    "paper_trading_positions",
    "paper_trading_orders",
    "paper_trading_trade_history",
)


def _drop_paper_engine_columns() -> None:
    """Drop engine-attribution columns and indexes from paper trading tables."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table in _PAPER_TABLES:
        if table not in tables:
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        indexes = {ix["name"] for ix in inspector.get_indexes(table)}
        # Single-column auto indexes created on the engine columns.
        for col in ENGINE_COLUMNS:
            idx = f"ix_{table}_{col}"
            if idx in indexes:
                try:
                    op.drop_index(idx, table_name=table)
                except Exception:
                    pass
        # Engine-specific composite indexes.
        for idx in (
            "idx_unique_open_position_engine",
            "idx_positions_account_engine_status",
            "idx_trade_history_account_engine_closed",
        ):
            if idx in indexes:
                try:
                    op.drop_index(idx, table_name=table)
                except Exception:
                    pass
        for name in ENGINE_COLUMNS:
            if name in cols:
                op.drop_column(table, name)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    # 1. Lab engine decision storage.
    if "recommendation_engine_decisions" in tables:
        op.drop_table("recommendation_engine_decisions")

    # 1b. Feature permission seed exclusively for the deleted Recommendation Lab.
    if "feature_permissions" in tables:
        op.execute(
            "DELETE FROM feature_permissions WHERE feature_key = 'recommendation_lab'"
        )

    # 2. Engine-attribution columns on paper trading tables.
    _drop_paper_engine_columns()

    # 3. Open-position uniqueness without the engine dimension.
    if "paper_trading_positions" in tables:
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        indexes = {ix["name"] for ix in inspector.get_indexes("paper_trading_positions")}
        if "idx_unique_open_position" not in indexes:
            op.create_index(
                "idx_unique_open_position",
                "paper_trading_positions",
                ["account_id", "symbol"],
                unique=True,
                postgresql_where=sa.text("status = 'OPEN'"),
            )


def downgrade() -> None:
    """Best-effort inverse: recreate the attribution columns (data is lost on drop).

    The ``recommendation_engine_decisions`` table is intentionally NOT
    recreated — the lab engine code that consumed it has been deleted.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "paper_trading_positions" in tables:
        indexes = {ix["name"] for ix in inspector.get_indexes("paper_trading_positions")}
        if "idx_unique_open_position" in indexes:
            try:
                op.drop_index("idx_unique_open_position", table_name="paper_trading_positions")
            except Exception:
                pass

    for table in _PAPER_TABLES:
        if table not in tables:
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        specs = (
            ("source_engine_id", sa.String(length=32)),
            ("source_engine_version", sa.String(length=32)),
            ("source_recommendation_id", sa.String(length=64)),
            ("experiment_id", sa.String(length=64)),
        )
        for name, col_type in specs:
            if name not in cols:
                op.add_column(table, sa.Column(name, col_type, nullable=True))
