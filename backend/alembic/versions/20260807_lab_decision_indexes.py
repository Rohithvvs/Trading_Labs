"""Additive indexes for Recommendation Lab scan/health aggregates.

Revision ID: 20260807_lab_decision_indexes
Revises: 20260807_auto_paper_engine
Create Date: 2026-08-07

Supports:
- list_recent_scan_runs GROUP BY (engine_id, scan_run_id)
- health windows on (engine_id, created_at)
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260807_lab_decision_indexes"
down_revision: Union[str, None] = "20260807_auto_paper_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "recommendation_engine_decisions"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if TABLE not in insp.get_table_names():
        return
    idxs = {i["name"] for i in insp.get_indexes(TABLE)}

    if "ix_rec_decisions_engine_scan_run" not in idxs:
        try:
            op.create_index(
                "ix_rec_decisions_engine_scan_run",
                TABLE,
                ["engine_id", "scan_run_id"],
                unique=False,
            )
        except Exception:
            op.execute(
                sa.text(
                    "CREATE INDEX IF NOT EXISTS ix_rec_decisions_engine_scan_run "
                    f"ON {TABLE} (engine_id, scan_run_id)"
                )
            )

    if "ix_rec_decisions_engine_created" not in idxs:
        try:
            op.create_index(
                "ix_rec_decisions_engine_created",
                TABLE,
                ["engine_id", "created_at"],
                unique=False,
            )
        except Exception:
            op.execute(
                sa.text(
                    "CREATE INDEX IF NOT EXISTS ix_rec_decisions_engine_created "
                    f"ON {TABLE} (engine_id, created_at)"
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if TABLE not in insp.get_table_names():
        return
    idxs = {i["name"] for i in insp.get_indexes(TABLE)}
    if "ix_rec_decisions_engine_created" in idxs:
        op.drop_index("ix_rec_decisions_engine_created", table_name=TABLE)
    if "ix_rec_decisions_engine_scan_run" in idxs:
        op.drop_index("ix_rec_decisions_engine_scan_run", table_name=TABLE)
