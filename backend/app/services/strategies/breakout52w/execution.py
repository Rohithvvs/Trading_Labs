"""Historical execution model for 52W book replay.

KERNEL (default) preserves the published 038 close-fill / close-cross trail.
TV_COMPAT models TradingView-style market-order timing: signal at bar close,
fill at the next bar's open, optional intrabar stop touch.

OHLC sequencing for DEFAULT_OHLC longs (no look-ahead):
1. If open gaps through the stop, fill at open.
2. Else if low touches the stop, fill at the stop price.
3. Targets are not used by this strategy. If a target and stop are both
   present, the stop is assumed to be touched first (conservative).
4. CLOSE_CROSS trails ignore intrabar lows and exit only when close < TSL.

LOWER_TIMEFRAME walks available lower-TF bars in timestamp order. Missing
lower-TF data falls back to DEFAULT_OHLC and is recorded — never fabricated.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from .identity import ALLOC_PCT, MAX_POSITIONS, STRATEGY_ID

OrderFillDelay = Literal["SAME_BAR_CLOSE", "NEXT_BAR_OPEN"]
HistoricalFillMode = Literal["DEFAULT_OHLC", "LOWER_TIMEFRAME"]
TrailTouch = Literal["CLOSE_CROSS", "INTRABAR_TOUCH"]
PositionLifecycle = Literal["FLAT", "ENTRY_PENDING", "LONG", "EXIT_PENDING"]
ExecutionProfile = Literal["KERNEL", "TV_COMPAT"]

ORDER_FILL_DELAYS: tuple[str, ...] = ("SAME_BAR_CLOSE", "NEXT_BAR_OPEN")
FILL_MODES: tuple[str, ...] = ("DEFAULT_OHLC", "LOWER_TIMEFRAME")
TRAIL_TOUCHES: tuple[str, ...] = ("CLOSE_CROSS", "INTRABAR_TOUCH")
PROFILES: tuple[str, ...] = ("KERNEL", "TV_COMPAT")
BACKTEST_END_REASON = "eod_liquidation"
BACKTEST_END_CANONICAL = "BACKTEST_END_LIQUIDATION"
ATR_TRAIL_REASON = "atr_trail"


@dataclass(frozen=True)
class ExecutionConfig:
    profile: ExecutionProfile = "KERNEL"
    order_fill_delay: OrderFillDelay = "SAME_BAR_CLOSE"
    historical_fill_mode: HistoricalFillMode = "DEFAULT_OHLC"
    trail_touch: TrailTouch = "CLOSE_CROSS"
    allow_entry_bar_exit: bool = False
    allow_same_bar_reentry: bool = False
    allow_reentry: bool = True
    pyramiding: int = 0
    max_positions: int = MAX_POSITIONS
    alloc_pct: float = ALLOC_PCT
    skip_on_missing_next_bar: bool = True
    slippage_rate: float = 0.0
    apply_costs: bool = True
    breakeven_tolerance_inr: float = 0.0
    conservative_stop_before_target: bool = True

    def hash(self) -> str:
        payload = {k: v for k, v in asdict(self).items()}
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def as_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["hash"] = self.hash()
        return data


KERNEL_EXECUTION = ExecutionConfig()
TV_COMPAT_EXECUTION = ExecutionConfig(
    profile="TV_COMPAT",
    order_fill_delay="NEXT_BAR_OPEN",
    historical_fill_mode="DEFAULT_OHLC",
    trail_touch="INTRABAR_TOUCH",
    allow_entry_bar_exit=True,
    allow_same_bar_reentry=False,
    skip_on_missing_next_bar=True,
)


def parse_execution_profile(
    raw: str | None,
    *,
    fill_mode: str | None = None,
) -> ExecutionConfig:
    key = (raw or "KERNEL").strip().upper()
    if key in {"TV", "TV_COMPAT", "TRADINGVIEW", "NEXT_BAR_OPEN"}:
        cfg = TV_COMPAT_EXECUTION
    else:
        cfg = KERNEL_EXECUTION
    mode = (fill_mode or cfg.historical_fill_mode).strip().upper()
    if mode in FILL_MODES and mode != cfg.historical_fill_mode:
        return ExecutionConfig(**{**asdict(cfg), "historical_fill_mode": mode})  # type: ignore[arg-type]
    return cfg


@dataclass(frozen=True)
class BarOHLC:
    session: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None = None


@dataclass(frozen=True)
class Fill:
    price: float
    reason: str
    gap: bool = False
    source: str = "DEFAULT_OHLC"


@dataclass
class ExecutionDiagnostics:
    lower_timeframe_requested: bool = False
    lower_timeframe_available: bool = False
    lower_timeframe_fallback: bool = False
    lower_timeframe_resolution: str | None = None
    missing_open_fallback: bool = False
    missing_open_count: int = 0
    skipped_pending_entries: int = 0
    failed_symbols: list[dict[str, Any]] = field(default_factory=list)
    skipped_symbols: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "lower_timeframe_requested": self.lower_timeframe_requested,
            "lower_timeframe_available": self.lower_timeframe_available,
            "lower_timeframe_fallback": self.lower_timeframe_fallback,
            "lower_timeframe_resolution": self.lower_timeframe_resolution,
            "missing_open_fallback": self.missing_open_fallback,
            "missing_open_count": self.missing_open_count,
            "skipped_pending_entries": self.skipped_pending_entries,
            "failed_symbols": list(self.failed_symbols),
            "skipped_symbols": list(self.skipped_symbols),
        }


def apply_slippage(price: float, *, side: str, rate: float) -> float:
    if rate <= 0:
        return float(price)
    if side.upper() in {"BUY", "LONG"}:
        return float(price) * (1.0 + rate)
    return float(price) * (1.0 - rate)


def long_stop_fill(bar: BarOHLC, stop: float) -> Fill | None:
    """Deterministic long stop using only this bar. Stop-before-target."""
    if stop is None:
        return None
    stop = float(stop)
    o = bar.open
    low = bar.low
    if o is not None and float(o) <= stop:
        return Fill(price=float(o), reason=ATR_TRAIL_REASON, gap=True)
    if low is not None and float(low) <= stop:
        return Fill(price=stop, reason=ATR_TRAIL_REASON, gap=False)
    return None


def close_cross_exit(bar: BarOHLC, stop: float) -> Fill | None:
    if bar.close is None:
        return None
    if float(bar.close) < float(stop):
        return Fill(price=float(bar.close), reason=ATR_TRAIL_REASON, gap=False)
    return None


def walk_lower_timeframe(
    bars: list[BarOHLC],
    stop: float,
) -> Fill | None:
    """First lower-TF bar that touches the stop. Ordered by session/time."""
    for bar in bars:
        hit = long_stop_fill(bar, stop)
        if hit is not None:
            return Fill(price=hit.price, reason=hit.reason, gap=hit.gap, source="LOWER_TIMEFRAME")
    return None


def resolve_exit_fill(
    bar: BarOHLC,
    stop: float,
    *,
    cfg: ExecutionConfig,
    lower_tf: list[BarOHLC] | None = None,
    diagnostics: ExecutionDiagnostics | None = None,
) -> Fill | None:
    if cfg.trail_touch == "CLOSE_CROSS":
        return close_cross_exit(bar, stop)
    if cfg.historical_fill_mode == "LOWER_TIMEFRAME":
        if diagnostics is not None:
            diagnostics.lower_timeframe_requested = True
        if lower_tf:
            if diagnostics is not None:
                diagnostics.lower_timeframe_available = True
            hit = walk_lower_timeframe(lower_tf, stop)
            if hit is not None:
                return hit
            # No touch on LTF — also no daily touch if LTF covers the session.
            daily = long_stop_fill(bar, stop)
            return daily
        if diagnostics is not None:
            diagnostics.lower_timeframe_fallback = True
    return long_stop_fill(bar, stop)


def entry_fill_price(
    bar: BarOHLC,
    *,
    cfg: ExecutionConfig,
    signal_close: float | None,
    diagnostics: ExecutionDiagnostics | None = None,
) -> float | None:
    if cfg.order_fill_delay == "NEXT_BAR_OPEN":
        if bar.open is not None and float(bar.open) > 0:
            return float(bar.open)
        if diagnostics is not None:
            diagnostics.missing_open_fallback = True
            diagnostics.missing_open_count += 1
        if cfg.skip_on_missing_next_bar:
            return None
        if bar.close is not None and float(bar.close) > 0:
            return float(bar.close)
        return None
    if signal_close is not None and float(signal_close) > 0:
        return float(signal_close)
    if bar.close is not None and float(bar.close) > 0:
        return float(bar.close)
    return None


def bar_from_maps(
    symbol: str,
    session: date,
    *,
    open_m: dict[str, dict[date, float]] | None,
    high_m: dict[str, dict[date, float]],
    low_m: dict[str, dict[date, float]],
    close_m: dict[str, dict[date, float]],
    vol_m: dict[str, dict[date, float]] | None = None,
) -> BarOHLC:
    return BarOHLC(
        session=session,
        open=(open_m or {}).get(symbol, {}).get(session),
        high=high_m.get(symbol, {}).get(session),
        low=low_m.get(symbol, {}).get(session),
        close=close_m.get(symbol, {}).get(session),
        volume=(vol_m or {}).get(symbol, {}).get(session),
    )


def ltf_session_bars(
    lower_tf: dict[str, list[dict[str, Any]]] | None,
    symbol: str,
    session: date,
) -> list[BarOHLC]:
    rows = (lower_tf or {}).get(symbol) or []
    out: list[BarOHLC] = []
    for row in rows:
        raw = row.get("timestamp") or row.get("session") or row.get("date")
        if raw is None:
            continue
        if isinstance(raw, datetime):
            sess = raw.date()
        elif isinstance(raw, date):
            sess = raw
        else:
            try:
                sess = date.fromisoformat(str(raw)[:10])
            except ValueError:
                continue
        if sess != session:
            continue
        out.append(
            BarOHLC(
                session=sess,
                open=_pos(row.get("open")),
                high=_pos(row.get("high")),
                low=_pos(row.get("low")),
                close=_pos(row.get("close")),
                volume=_pos(row.get("volume")),
            )
        )
    return out


def _pos(value: Any) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n != n:  # NaN
        return None
    return n


def record_symbol_failure(
    diagnostics: ExecutionDiagnostics,
    *,
    symbol: str,
    error_type: str,
    message: str,
    stage: str,
    duration_ms: int | None = None,
) -> None:
    diagnostics.failed_symbols.append(
        {
            "symbol": symbol,
            "error_type": error_type,
            "error_message": message,
            "stage": stage,
            "duration_ms": duration_ms,
            "strategy_id": STRATEGY_ID,
        }
    )
