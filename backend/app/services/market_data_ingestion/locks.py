"""Single-flight lock for strategy market-data FULL/DAILY loads."""
from __future__ import annotations

from ...db.locks import SingletonLease, acquire_singleton_lease

LOCK_NAME = "market_data:load"
# Full load can run long; daily update usually <15m. Lease safety TTL is high.
DEFAULT_MAX_LEASE_SECONDS = 6 * 3600.0


async def acquire_market_data_load_lock(
    max_lease_seconds: float = DEFAULT_MAX_LEASE_SECONDS,
) -> SingletonLease:
    return await acquire_singleton_lease(LOCK_NAME, max_lease_seconds=max_lease_seconds)
