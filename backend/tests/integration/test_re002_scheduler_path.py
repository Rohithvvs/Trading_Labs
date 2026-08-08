"""Scheduler/analysis path still invokes RE-002 when active (orchestrator wire)."""

from pathlib import Path


def test_orchestrator_wires_re002():
    path = Path(__file__).resolve().parents[2] / "app" / "agents" / "orchestrator_agent.py"
    text = path.read_text(encoding="utf-8")
    assert "is_re002_active" in text
    assert "run_re002_isolated_async" in text
    # Parallel lab gather present
    assert "asyncio.gather" in text
