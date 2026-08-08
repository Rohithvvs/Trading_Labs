"""RE-002 lab routes are registered under recommendation-lab prefix."""

from app.routes.re002_lab import router


def test_re002_routes_registered():
    paths = {getattr(r, "path", None) for r in router.routes}
    assert any(p and "/re002/registration" in p for p in paths)
    assert any(p and "/re002/scans/recent" in p for p in paths)
    assert any(p and "/re002/history" in p for p in paths)
    assert any(p and "/re002/health" in p for p in paths)
    assert any(p and "/re002/scans/{scan_run_id}/comparison" in p for p in paths)


def test_lab_access_dependency_present():
    # Every route should depend on lab access (feature permission)
    for r in router.routes:
        deps = getattr(r, "dependant", None)
        assert deps is not None
