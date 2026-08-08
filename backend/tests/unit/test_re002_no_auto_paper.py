"""RE-002 does not auto-create paper orders under PAPER_LINKED."""

from pathlib import Path

from app.services.re002.registry import get_re002_registration
from app.services.re002.runner import run_re002_isolated_async


def test_registration_has_no_auto_paper_flag():
    reg = get_re002_registration()
    data = reg.model_dump()
    assert "auto_paper" not in data
    assert "auto_trade" not in data


def test_runner_has_no_paper_order_side_effect():
    """Static guard: runner module must not place paper orders."""
    path = Path(__file__).resolve().parents[2] / "app" / "services" / "re002" / "runner.py"
    text = path.read_text(encoding="utf-8")
    assert "place_order" not in text
    assert "paper_trading" not in text
    assert "from_recommendation" not in text
    # API exists for isolation but is not a paper order API
    assert "run_re002_isolated_async" in text
