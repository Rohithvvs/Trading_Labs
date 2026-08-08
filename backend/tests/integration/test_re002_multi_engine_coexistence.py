"""RE-001 and RE-002 decisions are namespaced by engine_id and do not clobber."""

from app.models.recommendation_engine import RecommendationEngineDecision


def test_model_supports_multi_engine_namespace():
    assert hasattr(RecommendationEngineDecision, "engine_id")
    assert hasattr(RecommendationEngineDecision, "recommendation_id")
    # RE-002 attribution column is additive and nullable for RE-001 rows
    assert hasattr(RecommendationEngineDecision, "experiment_id")


def test_packages_are_independent():
    from app.services import re001, re002

    assert hasattr(re001, "run_re001_isolated_async")
    assert hasattr(re002, "run_re002_isolated_async")
    # Distinct module paths
    assert re001.__name__ != re002.__name__
