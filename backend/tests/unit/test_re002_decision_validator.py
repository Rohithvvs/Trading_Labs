"""RE-002 decision validator."""

from app.schemas.re002 import Re002DecisionObject
from app.services.re002.decision_validator import validate_decision_object


def test_valid_reject():
    obj = Re002DecisionObject(
        recommendation_id="abc-123-def",
        recommendation_state="REJECT",
        confidence_score=0.1,
        reason_codes=["weak_relative_strength"],
    )
    ok, errs = validate_decision_object(obj)
    assert ok, errs


def test_buy_requires_strategy():
    obj = Re002DecisionObject(
        recommendation_id="abc-123-def",
        recommendation_state="BUY",
        confidence_score=0.8,
        market_regime="Bull",
    )
    ok, errs = validate_decision_object(obj)
    assert not ok
    assert "missing_primary_strategy" in errs


def test_invalid_engine_id():
    obj = Re002DecisionObject(
        recommendation_id="abc-123-def",
        engine_id="RE-001",
        recommendation_state="REJECT",
        confidence_score=0.0,
    )
    ok, errs = validate_decision_object(obj)
    assert not ok
    assert "invalid_engine_id" in errs
