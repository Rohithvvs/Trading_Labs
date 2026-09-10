import asyncio
import logging

import pytest

from backend.app.core.task_supervisor import TaskSupervisor


@pytest.mark.asyncio
async def test_shutdown_does_not_log_crash_when_session_close_fails(caplog):
    supervisor = TaskSupervisor()
    started = asyncio.Event()

    async def _job():
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise RuntimeError(
                "cannot call Transaction.rollback(): the underlying connection is closed"
            ) from None

    with caplog.at_level(logging.WARNING, logger="app.task_supervisor"):
        supervisor.start("gap-replay", _job)
        await started.wait()
        await supervisor.shutdown()

    assert supervisor._closing is True
    assert not any("Supervised task crashed" in rec.message for rec in caplog.records)
    assert any("stopped during shutdown" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_crash_is_logged_when_not_shutting_down(caplog):
    supervisor = TaskSupervisor()
    crashed = asyncio.Event()

    async def _job():
        crashed.set()
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR, logger="app.task_supervisor"):
        supervisor.start("flaky", _job)
        await crashed.wait()
        await asyncio.sleep(0.05)
        await supervisor.shutdown()

    assert any("Supervised task crashed" in rec.message for rec in caplog.records)
