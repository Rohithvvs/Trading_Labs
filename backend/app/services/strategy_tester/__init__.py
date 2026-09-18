"""Configurable Strategy Tester: deterministic evaluation of user-defined strategies.

Trading indicators, filter pass/fail, BUY/WATCH/REJECT classification, and
return calculations are computed in process. No LLM is used for any of those
steps. Indicator values at timestamp t use only bars with index <= t.
"""

from .schema import (
    CALCULATION_VERSION,
    DEFAULT_UNIVERSE,
    FilterNode,
    Operand,
    StrategyDefinitionConfig,
    parse_strategy_config,
)
from .engine import StrategyEvaluationResult, evaluate_stock
from .scan_service import start_test_background

__all__ = [
    "CALCULATION_VERSION",
    "DEFAULT_UNIVERSE",
    "FilterNode",
    "Operand",
    "StrategyDefinitionConfig",
    "StrategyEvaluationResult",
    "evaluate_stock",
    "parse_strategy_config",
    "start_test_background",
]
