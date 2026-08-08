"""Paper order/position models carry structured lab provenance (FR-029)."""

from app.models.paper_trading import PaperOrder, PaperPosition
from app.schemas.paper_trading import PaperOrderCreateRequest, RecommendationPrefillResponse


def test_paper_order_model_has_provenance_columns():
    assert hasattr(PaperOrder, "source_engine_id")
    assert hasattr(PaperOrder, "source_engine_version")
    assert hasattr(PaperOrder, "source_recommendation_id")
    assert hasattr(PaperOrder, "experiment_id")


def test_paper_position_model_has_provenance_columns():
    assert hasattr(PaperPosition, "source_engine_id")
    assert hasattr(PaperPosition, "source_recommendation_id")
    assert hasattr(PaperPosition, "experiment_id")


def test_create_request_accepts_re002_provenance():
    req = PaperOrderCreateRequest(
        idempotency_key="k" * 16,
        symbol="INFY",
        side="BUY",
        type="LIMIT",
        qty=1,
        limit_price=100.0,
        source_engine_id="RE-002",
        source_engine_version="1.0",
        source_recommendation_id="rec-12345678",
        experiment_id="exp-re002",
    )
    assert req.source_engine_id == "RE-002"
    assert req.experiment_id == "exp-re002"


def test_prefill_response_includes_experiment_id():
    resp = RecommendationPrefillResponse(
        symbol="INFY",
        note="Imported from RE-002",
        source_engine_id="RE-002",
        source_recommendation_id="rec-1",
        experiment_id="exp-1",
    )
    assert resp.experiment_id == "exp-1"
