"""Auto paper trading: engine-scoped open positions + trade history provenance.

Revision ID: 20260807_auto_paper_engine
Revises: 20260805_perf_indexes
Create Date: 2026-08-07

- Backfill source_engine_id NULL → 'Production' on orders/positions
- Make source_engine_id NOT NULL with default Production
- Replace unique open position index: (account, symbol) → (account, symbol, engine)
- Add source_engine_* columns on paper_trading_trade_history
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260807_auto_paper_engine"
down_revision: Union[str, None] = "20260805_perf_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector: sa.Inspector, table: str) -> bool:
    return table in inspector.get_table_names()


def _cols(inspector: sa.Inspector, table: str) -> set[str]:
    if not _table_exists(inspector, table):
        return set()
    return {c["name"] for c in inspector.get_columns(table)}


def _indexes(inspector: sa.Inspector, table: str) -> set[str]:
    if not _table_exists(inspector, table):
        return set()
    return {ix["name"] for ix in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table in ("paper_trading_orders", "paper_trading_positions"):
        if not _table_exists(inspector, table):
            continue
        cols = _cols(inspector, table)
        if "source_engine_id" not in cols:
            op.add_column(
                table,
                sa.Column("source_engine_id", sa.String(length=32), nullable=True),
            )
            op.execute(
                sa.text(
                    f"UPDATE {table} SET source_engine_id = 'Production' "
                    f"WHERE source_engine_id IS NULL"
                )
            )
        else:
            op.execute(
                sa.text(
                    f"UPDATE {table} SET source_engine_id = 'Production' "
                    f"WHERE source_engine_id IS NULL OR TRIM(source_engine_id) = ''"
                )
            )
        # Normalize known aliases
        op.execute(
            sa.text(
                f"""
                UPDATE {table}
                SET source_engine_id = CASE
                    WHEN UPPER(TRIM(source_engine_id)) IN ('PRODUCTION', 'PROD', 'BASELINE', 'SYSTEM')
                        THEN 'Production'
                    WHEN UPPER(REPLACE(TRIM(source_engine_id), '_', '-')) IN ('RE-001', 'RE001')
                        THEN 'RE-001'
                    WHEN UPPER(REPLACE(TRIM(source_engine_id), '_', '-')) IN ('RE-002', 'RE002')
                        THEN 'RE-002'
                    ELSE source_engine_id
                END
                """
            )
        )
        try:
            op.alter_column(
                table,
                "source_engine_id",
                existing_type=sa.String(length=32),
                nullable=False,
                server_default=sa.text("'Production'"),
            )
        except Exception:
            # SQLite / partial dialects: best-effort
            pass

    # Trade history provenance
    table = "paper_trading_trade_history"
    if _table_exists(inspector, table):
        cols = _cols(inspector, table)
        specs = [
            ("source_engine_id", sa.Column("source_engine_id", sa.String(length=32), nullable=True)),
            ("source_engine_version", sa.Column("source_engine_version", sa.String(length=32), nullable=True)),
            ("source_recommendation_id", sa.Column("source_recommendation_id", sa.String(length=64), nullable=True)),
            ("experiment_id", sa.Column("experiment_id", sa.String(length=64), nullable=True)),
        ]
        for name, col in specs:
            if name not in cols:
                op.add_column(table, col)
        op.execute(
            sa.text(
                "UPDATE paper_trading_trade_history "
                "SET source_engine_id = 'Production' "
                "WHERE source_engine_id IS NULL OR TRIM(source_engine_id) = ''"
            )
        )
        try:
            op.alter_column(
                table,
                "source_engine_id",
                existing_type=sa.String(length=32),
                nullable=False,
                server_default=sa.text("'Production'"),
            )
        except Exception:
            pass
        inspector = sa.inspect(bind)
        idxs = _indexes(inspector, table)
        if "ix_paper_trading_trade_history_source_engine_id" not in idxs:
            try:
                op.create_index(
                    "ix_paper_trading_trade_history_source_engine_id",
                    table,
                    ["source_engine_id"],
                    unique=False,
                )
            except Exception:
                pass
        if "idx_trade_history_account_engine_closed" not in idxs:
            try:
                op.create_index(
                    "idx_trade_history_account_engine_closed",
                    table,
                    ["account_id", "source_engine_id", "closed_at"],
                    unique=False,
                )
            except Exception:
                pass

    # Positions: replace unique open index to include engine
    pos_table = "paper_trading_positions"
    if _table_exists(inspector, pos_table):
        inspector = sa.inspect(bind)
        idxs = _indexes(inspector, pos_table)
        # Drop legacy unique-by-symbol-only index if present
        for legacy in ("idx_unique_open_position", "ix_paper_trading_positions_unique_open"):
            if legacy in idxs:
                try:
                    op.drop_index(legacy, table_name=pos_table)
                except Exception:
                    try:
                        op.execute(sa.text(f"DROP INDEX IF EXISTS {legacy}"))
                    except Exception:
                        pass
        inspector = sa.inspect(bind)
        idxs = _indexes(inspector, pos_table)
        if "idx_unique_open_position_engine" not in idxs:
            try:
                op.execute(
                    sa.text(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_open_position_engine
                        ON paper_trading_positions (account_id, symbol, source_engine_id)
                        WHERE status = 'OPEN'
                        """
                    )
                )
            except Exception:
                pass
        if "idx_positions_account_engine_status" not in idxs:
            try:
                op.create_index(
                    "idx_positions_account_engine_status",
                    pos_table,
                    ["account_id", "source_engine_id", "status"],
                    unique=False,
                )
            except Exception:
                pass


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    pos_table = "paper_trading_positions"
    if _table_exists(inspector, pos_table):
        try:
            op.drop_index("idx_unique_open_position_engine", table_name=pos_table)
        except Exception:
            try:
                op.execute(sa.text("DROP INDEX IF EXISTS idx_unique_open_position_engine"))
            except Exception:
                pass
        try:
            op.execute(
                sa.text(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_open_position
                    ON paper_trading_positions (account_id, symbol)
                    WHERE status = 'OPEN'
                    """
                )
            )
        except Exception:
            pass
        try:
            op.drop_index("idx_positions_account_engine_status", table_name=pos_table)
        except Exception:
            pass

    table = "paper_trading_trade_history"
    if _table_exists(inspector, table):
        for idx in (
            "idx_trade_history_account_engine_closed",
            "ix_paper_trading_trade_history_source_engine_id",
        ):
            try:
                op.drop_index(idx, table_name=table)
            except Exception:
                pass
        cols = _cols(inspector, table)
        for name in (
            "experiment_id",
            "source_recommendation_id",
            "source_engine_version",
            "source_engine_id",
        ):
            if name in cols:
                try:
                    op.drop_column(table, name)
                except Exception:
                    pass
