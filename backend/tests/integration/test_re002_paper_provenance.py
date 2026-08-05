"""Paper prefill path accepts RE-002 provenance fields."""

from app.schemas.paper_trading import RecommendationPrefillRequest, RecommendationPrefillResponse
from app.services.paper_trading_service import PaperTradingService


def test_prefill_request_schema_multi_engine():
    req = RecommendationPrefillRequest(
        symbol="INFY",
        suggested_entry=100.0,
        suggested_stop=95.0,
        suggested_targets=[110.0],
        recommendation_meta={"signal": "BUY", "score": 80, "confidence": 0.7},
        source_engine_id="RE-002",
        source_engine_version="1.0",
        source_recommendation_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        experiment_id="exp-re002",
    )
    assert req.source_engine_id == "RE-002"
    assert req.experiment_id == "exp-re002"


def test_prefill_note_includes_engine_without_db(monkeypatch):
    """recommendation_prefill with no DB row still stamps engine in note."""

    class _DB:
        def scalar(self, *a, **k):
            return None

    svc = PaperTradingService.__new__(PaperTradingService)
    svc.db = _DB()
    svc.user_id = None

    # Avoid DB lookup path errors by leaving recommendation_id empty
    from app.schemas.paper_trading import RecommendationPrefillRequest

    payload = RecommendationPrefillRequest(
        symbol="INFY",
        suggested_entry=100.0,
        suggested_stop=95.0,
        suggested_targets=[110.0],
        recommendation_meta={"signal": "BUY", "score": 70, "confidence": 0.6},
        source_engine_id="RE-002",
        source_engine_version="1.0",
        experiment_id="exp-1",
    )
    # Patch get_decision to avoid import side effects if engine path triggers
    resp = PaperTradingService.recommendation_prefill(svc, payload)
    assert isinstance(resp, RecommendationPrefillResponse)
    assert resp.source_engine_id == "RE-002"
    assert "RE-002" in resp.note
    assert resp.experiment_id == "exp-1"
