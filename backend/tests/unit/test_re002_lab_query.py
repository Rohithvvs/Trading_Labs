"""RE-002 lab query helpers (history / recent scans signatures)."""

from app.services.re002 import lab_query


def test_exports():
    assert callable(lab_query.list_recent_scan_runs)
    assert callable(lab_query.list_history)
    assert callable(lab_query.scan_comparison)
    assert callable(lab_query.latest_for_symbol)


def test_history_payload_shape_empty_db_session():
    """When db raises, history should not be used without session — just API shape via mock."""

    class _Q:
        def filter(self, *a, **k):
            return self

        def count(self):
            return 0

        def order_by(self, *a, **k):
            return self

        def offset(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def all(self):
            return []

    class _DB:
        def query(self, *a, **k):
            return _Q()

    out = lab_query.list_history(_DB(), limit=10, offset=0)
    assert out["engine_id"] == "RE-002"
    assert out["total"] == 0
    assert out["items"] == []
    assert out["limit"] == 10
