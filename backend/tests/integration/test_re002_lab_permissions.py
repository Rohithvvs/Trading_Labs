"""RE-002 lab routes declare feature permission dependency (recommendation_lab)."""

from app.routes import re002_lab


def test_lab_access_uses_recommendation_lab_feature():
    src = open(re002_lab.__file__, encoding="utf-8").read()
    assert 'require_feature_sync("recommendation_lab")' in src
    assert "re002_ui_enabled" in src
