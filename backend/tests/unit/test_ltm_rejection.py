from app.services.strategies.ltm.rejection import breakdown, first_failure


def test_precedence_insufficient_history_before_gate():
    code = first_failure(
        in_universe=True,
        close_t=200.0,
        close_t_minus_252=None,
    )
    assert code == "insufficient_history"


def test_ranked_out_after_gate():
    code = first_failure(
        in_universe=True,
        close_t=200.0,
        close_t_minus_252=100.0,
        eligible_rank=11,
    )
    assert code == "ranked_outside_top_10"


def test_selected_has_no_failure():
    assert (
        first_failure(
            in_universe=True,
            close_t=200.0,
            close_t_minus_252=100.0,
            eligible_rank=3,
        )
        is None
    )


def test_breakdown_single_count():
    rows = breakdown(["failed_momentum_gate", "failed_momentum_gate", "not_in_universe"], 10)
    by_code = {r["code"]: r for r in rows}
    assert by_code["failed_momentum_gate"]["count"] == 2
    assert by_code["not_in_universe"]["count"] == 1
    assert abs(by_code["failed_momentum_gate"]["pct"] - 20.0) < 0.01
