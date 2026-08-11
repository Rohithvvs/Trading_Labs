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
    """Static guard: runner must not place orders DIRECTLY.

    RE-002 (like RE-001) only auto-papers BUY decisions through the sanctioned
    fail-open ``maybe_auto_paper_from_lab_decision`` hook — never a direct
    ``place_order`` call.
    """
    path = Path(__file__).resolve().parents[2] / "app" / "services" / "re002" / "runner.py"
    text = path.read_text(encoding="utf-8")
    assert "place_order" not in text
    assert "from_recommendation" not in text
    # Only the sanctioned lab auto-paper hook may appear
    if "auto_paper" in text:
        assert "maybe_auto_paper_from_lab_decision" in text
    # API exists for isolation but is not a paper order API
    assert "run_re002_isolated_async" in text
