from app.services.strategies.breakout52w.identity import STRATEGY_ID
from app.services.strategies.ltm.identity import STRATEGY_ID as LTM_ID


def test_strategy_ids_differ():
    assert STRATEGY_ID == "09_52w_breakout"
    assert LTM_ID == "17_long_term_mom"
    assert STRATEGY_ID != LTM_ID


def test_w52_package_does_not_import_ltm_clock():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "app" / "services" / "strategies" / "breakout52w"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "strategies.ltm" not in node.module
                assert not node.module.startswith("app.services.strategies.ltm")
