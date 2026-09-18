"""Persist the 21 research-lab Pine scans as the user's Indicator Scanner library."""

from __future__ import annotations

import uuid
from typing import Any

from ..indicator_scanner.compiler import compile_source
from ..indicator_scanner.entry_conditions import attach_entry_conditions
from ..indicator_scanner.limits import LANGUAGE_MODE
from ..indicator_scanner import persistence
from .catalog import LAB_STRATEGIES
from .pine_catalog import pine_source_for


_TEMPLATE_CACHE: list[dict[str, Any]] | None = None


def template_payloads() -> list[dict[str, Any]]:
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is not None:
        return _TEMPLATE_CACHE
    rows: list[dict[str, Any]] = []
    for spec in LAB_STRATEGIES:
        source = pine_source_for(spec)
        compiled = compile_source(source)
        parsed = attach_entry_conditions(compiled.to_definition_json(), compiled)
        rows.append(
            {
                "strategy_id": spec.strategy_id,
                "number": spec.number,
                "name": spec.scan_title,
                "description": spec.description,
                "rank": spec.rank,
                "pine_kind": spec.pine_kind,
                "source_code": source,
                "timeframe": "1D",
                "script_version": compiled.version,
                "language_mode": compiled.language_mode,
                "required_bars": compiled.required_bars,
                "parsed_definition": parsed,
                "entry_conditions": parsed.get("entry_conditions") or [],
                "inputs": [item.to_dict() for item in compiled.inputs],
                "outputs": [item.to_dict() for item in compiled.outputs],
            }
        )
    _TEMPLATE_CACHE = rows
    return rows


async def seed_lab_indicators(user_id: uuid.UUID) -> dict[str, Any]:
    created: list[str] = []
    skipped: list[str] = []
    indicators: list[dict[str, Any]] = []
    for spec in LAB_STRATEGIES:
        existing = await persistence.find_definition_by_name(user_id, spec.scan_title)
        if existing is not None:
            skipped.append(spec.strategy_id)
            indicators.append(persistence.definition_payload(existing))
            continue
        source = pine_source_for(spec)
        compiled = compile_source(source)
        parsed = attach_entry_conditions(compiled.to_definition_json(), compiled)
        row = await persistence.create_definition(
            user_id=user_id,
            name=spec.scan_title,
            description=spec.description,
            source_code=source,
            script_version=int(compiled.version or 6),
            language_mode=LANGUAGE_MODE,
            timeframe="1D",
            parsed_definition=parsed,
            validation_status="valid",
            validation_errors=[],
            required_bars=int(compiled.required_bars),
        )
        created.append(spec.strategy_id)
        indicators.append(persistence.definition_payload(row))
    return {
        "created": created,
        "skipped": skipped,
        "count": len(indicators),
        "indicators": indicators,
    }
