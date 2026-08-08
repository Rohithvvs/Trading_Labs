"""RE-002 analytics health_segment uses SQL aggregates and returns expected keys."""

from app.services.re002.analytics import health_segment


class _Row:
    total = 0
    buy_count = 0
    watch_count = 0
    reject_count = 0
    error_count = 0
    timeout_count = 0
    mismatch_count = 0


class _AggQ:
    def filter(self, *a, **k):
        return self

    def one(self):
        return _Row()

    def limit(self, *a, **k):
        return self

    def all(self):
        return []


class _DB:
    def query(self, *a, **k):
        return _AggQ()


def test_health_segment_keys():
    out = health_segment(_DB(), window_hours=24)
    assert out["engine_id"] == "RE-002"
    assert out["total"] == 0
    assert out["buy_count"] == 0
    assert out["runtime_counters_authoritative"] is False
    assert "avg_rs_of_buys" in out
