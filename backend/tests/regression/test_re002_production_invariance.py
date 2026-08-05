"""Baseline recommendation path must not be owned by RE-002."""

from pathlib import Path


def _backend_root() -> Path:
    # tests/regression -> tests -> backend
    return Path(__file__).resolve().parents[2]


def test_recommendation_service_has_no_re002_writes():
    path = _backend_root() / "app" / "services" / "recommendation_service.py"
    text = path.read_text(encoding="utf-8")
    assert "RE-002" not in text
    assert "re002" not in text.lower()


def test_orchestrator_lab_hook_is_fail_open():
    """Orchestrator must catch lab failures and keep production path."""
    path = _backend_root() / "app" / "agents" / "orchestrator_agent.py"
    text = path.read_text(encoding="utf-8")
    assert "run_re002_isolated_async" in text
    assert "production path unchanged" in text
    # Lab engines must not assign production recommendation from RE-002
    assert "recommendation = re002" not in text.replace(" ", "").lower()


def test_re002_does_not_mutate_production_fields_in_package():
    """RE-002 package must not import or call production RecommendationService."""
    re002_dir = _backend_root() / "app" / "services" / "re002"
    for py in re002_dir.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert "from app.services.recommendation_service" not in text
        assert "import recommendation_service" not in text
        assert "RecommendationService(" not in text
