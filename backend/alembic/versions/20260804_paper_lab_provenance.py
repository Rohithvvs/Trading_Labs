"""Add lab engine provenance columns to paper orders and positions.

Revision ID: 20260804_paper_lab_provenance
Revises: 20260804_re002_experiment_id
Create Date: 2026-08-04
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_paper_lab_provenance"
down_revision: Union[str, None] = "20260804_re002_experiment_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_provenance_columns(table: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()
    if table not in tables:
        raise RuntimeError(
            f"Expected table {table!r} for lab provenance migration; refusing silent no-op."
        )
    cols = {c["name"] for c in inspector.get_columns(table)}
    specs = [
        ("source_engine_id", sa.Column("source_engine_id", sa.String(length=32), nullable=True)),
        ("source_engine_version", sa.Column("source_engine_version", sa.String(length=32), nullable=True)),
        ("source_recommendation_id", sa.Column("source_recommendation_id", sa.String(length=64), nullable=True)),
        ("experiment_id", sa.Column("experiment_id", sa.String(length=64), nullable=True)),
    ]
    for name, col in specs:
        if name not in cols:
            op.add_column(table, col)
    # Refresh column/index set after adds
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns(table)}
    indexes = {ix["name"] for ix in inspector.get_indexes(table)}
    for col_name, idx_name in (
        ("source_engine_id", f"ix_{table}_source_engine_id"),
        ("source_recommendation_id", f"ix_{table}_source_recommendation_id"),
        ("experiment_id", f"ix_{table}_experiment_id"),
    ):
        if col_name in cols and idx_name not in indexes:
            try:
                op.create_index(idx_name, table, [col_name], unique=False)
            except Exception:
                pass


def upgrade() -> None:
    _add_provenance_columns("paper_trading_orders")
    _add_provenance_columns("paper_trading_positions")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in ("paper_trading_orders", "paper_trading_positions"):
        if table not in inspector.get_table_names():
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        for idx in (
            f"ix_{table}_source_engine_id",
            f"ix_{table}_source_recommendation_id",
            f"ix_{table}_experiment_id",
        ):
            try:
                op.drop_index(idx, table_name=table)
            except Exception:
                pass
        for name in (
            "experiment_id",
            "source_recommendation_id",
            "source_engine_version",
            "source_engine_id",
        ):
            if name in cols:
                op.drop_column(table, name)
