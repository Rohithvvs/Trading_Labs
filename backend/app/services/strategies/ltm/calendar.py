"""Master-calendar session index and 252-session rebalance clock."""

from __future__ import annotations

from datetime import date

from .identity import REBALANCE_EVERY, WARMUP_SESSIONS


def clock_status(
    session_index: int,
    last_rebalance_index: int | None,
    *,
    warmup: int = WARMUP_SESSIONS,
    every: int = REBALANCE_EVERY,
) -> tuple[str, int, bool]:
    """Return (status, sessions_since_rebalance, fire).

    First rebalance is the first session with ``session_index >= warmup``.
    Subsequent fires occur every ``every`` sessions after the last fire.
    """
    if session_index < warmup:
        return "WARMUP", 0, False
    if last_rebalance_index is None:
        return "REBALANCE", 0, True
    since = session_index - last_rebalance_index
    if since >= every:
        return "REBALANCE", 0, True
    return "MID_CYCLE", since, False


def sessions_to_rebalance(
    session_index: int,
    last_rebalance_index: int | None,
    *,
    warmup: int = WARMUP_SESSIONS,
    every: int = REBALANCE_EVERY,
) -> int:
    status, since, _fire = clock_status(
        session_index, last_rebalance_index, warmup=warmup, every=every
    )
    if status == "WARMUP":
        return max(warmup - session_index, 0)
    if status == "REBALANCE":
        return 0
    return max(every - since, 0)


def estimate_next_rebalance_date(
    dates: list[date],
    session_index: int,
    last_rebalance_index: int | None,
) -> date | None:
    remaining = sessions_to_rebalance(session_index, last_rebalance_index)
    target = session_index + remaining
    if 0 <= target < len(dates):
        return dates[target]
    return None
