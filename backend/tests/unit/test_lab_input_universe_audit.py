"""Regression: build_lab_input_universe audit contract vs orchestrator logging.

The scanner failed after TA with:

  TypeError: object of type 'int' has no len()

at orchestrator_agent._run_screener_stage when logging:

  len(lab_input_audit.get("missing_from_data_valid") or [])

because build_lab_input_universe stores missing_from_data_valid as an INT COUNT.
When the count is > 0 it is truthy, so `or []` does not fire and len(int) raises.
"""

from __future__ import annotations

import logging

import pytest

from app.services.independent_lab_universe import build_lab_input_universe


def test_build_lab_input_universe_missing_is_int_count_not_list():
    source = [f"S{i}" for i in range(10)]
    data_valid = [f"S{i}" for i in range(7)]  # 3 missing

    audit = build_lab_input_universe(source, data_valid)

    assert audit["universe"] == source
    assert audit["universe_size"] == 10
    assert audit["data_valid_size"] == 7
    assert isinstance(audit["missing_from_data_valid"], int)
    assert audit["missing_from_data_valid"] == 3
    assert not isinstance(audit["missing_from_data_valid"], list)


def test_build_lab_input_universe_full_overlap_zero_missing():
    source = ["A", "B", "C"]
    audit = build_lab_input_universe(source, source)
    assert audit["missing_from_data_valid"] == 0
    assert audit["universe_size"] == 3
    assert audit["data_valid_size"] == 3


def test_build_lab_input_universe_empty_inputs():
    audit = build_lab_input_universe([], [])
    assert audit["universe"] == []
    assert audit["universe_size"] == 0
    assert audit["data_valid_size"] == 0
    assert audit["missing_from_data_valid"] == 0


def test_build_lab_input_universe_none_safe():
    audit = build_lab_input_universe(None, None)  # type: ignore[arg-type]
    assert audit["universe_size"] == 0
    assert audit["missing_from_data_valid"] == 0


def test_missing_from_data_valid_must_not_be_passed_to_len():
    """Reproduce the exact failure mode: len(count) when count > 0."""
    audit = build_lab_input_universe(
        [f"S{i}" for i in range(755)],
        [f"S{i}" for i in range(713)],  # 42 missing — mirrors real scan
    )
    count = audit["missing_from_data_valid"]
    assert count == 42

    # Legacy buggy pattern (must raise):
    with pytest.raises(TypeError, match="has no len"):
        len(audit.get("missing_from_data_valid") or [])

    # Correct contract usage:
    safe = int(audit.get("missing_from_data_valid") or 0)
    assert safe == 42


def test_lab_input_universe_log_format_accepts_int_count(caplog):
    """Orchestrator-style log must accept the int count without TypeError."""
    source = [f"S{i}" for i in range(50)]
    data_valid = [f"S{i}" for i in range(40)]
    audit = build_lab_input_universe(source, data_valid)
    missing_from_data_valid_count = int(audit.get("missing_from_data_valid") or 0)

    logger = logging.getLogger("test.lab_input_audit")
    with caplog.at_level(logging.INFO, logger="test.lab_input_audit"):
        logger.info(
            "LAB_INPUT_UNIVERSE | stage=%s | source=%s | data_valid=%s | missing_from_data_valid=%s | "
            "reason=re001_receives_full_stage_universe",
            "NIFTY500",
            len(source),
            len(data_valid),
            missing_from_data_valid_count,
        )

    assert "missing_from_data_valid=10" in caplog.text
    assert "source=50" in caplog.text


def test_re001_universe_remains_full_stage_not_top_n():
    """RE-001 input size must equal full stage universe (not Production top-N)."""
    source = [f"U{i}" for i in range(755)]
    data_valid = [f"U{i}" for i in range(700)]
    top_n = 20
    matched = data_valid[:241]
    production_shortlist = matched[:top_n]

    audit = build_lab_input_universe(source, data_valid)
    lab_input = list(audit["universe"])

    assert len(lab_input) == 755
    assert len(production_shortlist) == 20
    assert lab_input != production_shortlist
    assert audit["missing_from_data_valid"] == 55
