"""Strategy Comparison HTTP API. Reads existing Strategy Tester / LEAN data only."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core.deps import require_feature
from ..models.auth import User
from ..services.strategy_comparison.comparison_service import (
    MAX_SLOTS,
    MIN_SLOTS,
    CompareError,
    catalog,
    compare_slots,
    list_runs_for_strategy,
)

router = APIRouter(prefix="/strategy-comparison", tags=["strategy-comparison"])


class CompareSlotBody(BaseModel):
    strategy_id: str
    run_id: str
    source: Literal["strategy_tester", "lean"] | None = None


class CompareBody(BaseModel):
    slots: list[CompareSlotBody] = Field(min_length=MIN_SLOTS, max_length=MAX_SLOTS)


def _raise(exc: CompareError) -> None:
    raise HTTPException(status_code=exc.status_code, detail={"message": exc.message}) from exc


@router.get("/catalog")
async def get_catalog(user: User = Depends(require_feature("advanced_scanner"))) -> dict[str, Any]:
    return await catalog(user.id)


@router.get("/strategies/{strategy_id}/runs")
async def get_strategy_runs(
    strategy_id: str,
    user: User = Depends(require_feature("advanced_scanner")),
) -> dict[str, Any]:
    try:
        return await list_runs_for_strategy(user.id, strategy_id)
    except CompareError as exc:
        _raise(exc)
        raise


@router.post("")
async def create_comparison(
    body: CompareBody,
    user: User = Depends(require_feature("advanced_scanner")),
) -> dict[str, Any]:
    try:
        return await compare_slots(
            user.id,
            [slot.model_dump() for slot in body.slots],
        )
    except CompareError as exc:
        _raise(exc)
        raise
