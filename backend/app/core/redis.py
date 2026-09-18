import redis.asyncio as redis
from typing import Optional
import os
import logging
import subprocess
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger("app.redis")

REDIS_URL = os.getenv("REDIS_URL", "")
redis_client = None

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
# None = not resolved yet; "" = WSL IP unavailable this process.
_wsl_ipv4_cache: Optional[str] = None


def _connect_timeout_seconds() -> float:
    """TCP handshake timeout.

    Do not reuse the cache SET write budget (default 100ms): WSL-forwarded
    localhost and a freshly started Redis often exceed that, and a too-short
    connect timeout leaves a half-open client that later pings also fail.
    """
    return 1.0


def _create_redis_client(url: str):
    """Create async Redis client with connect timeout (op timeouts enforced by callers)."""
    return redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=_connect_timeout_seconds(),
        socket_timeout=_connect_timeout_seconds(),
        health_check_interval=30,
    )


def _wsl_rewrite_enabled() -> bool:
    flag = (os.getenv("REDIS_WSL_REWRITE") or "1").strip().lower()
    return flag not in {"0", "false", "no", "off"}


def reset_wsl_ipv4_cache() -> None:
    """Drop the cached WSL IP (call when the Redis client is disposed)."""
    global _wsl_ipv4_cache
    _wsl_ipv4_cache = None


def discover_wsl_ipv4(*, force: bool = False) -> str:
    """Best-effort WSL2 IPv4, or empty when WSL is absent.

    Cached for the process. Windows ``redis.asyncio`` cannot reliably connect
    through the WSL localhost relay (timeout / WSAEINVAL); the eth0 address
    works. ``force=True`` re-runs discovery after WSL restarts and changes IP.
    """
    global _wsl_ipv4_cache
    if os.name != "nt":
        return ""
    if not force and _wsl_ipv4_cache is not None:
        return _wsl_ipv4_cache
    ip = ""
    try:
        # Direct wsl.exe from Python hangs or returns Wsl/Service/E_UNEXPECTED
        # (no console / pipe handshake). cmd.exe /c is ~250ms and reliable.
        completed = subprocess.run(
            ["cmd.exe", "/c", "wsl -e hostname -I"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        for token in (completed.stdout or "").split():
            parts = token.split(".")
            if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                ip = token
                break
    except Exception as exc:
        logger.debug("WSL IP discovery failed: %s", exc)
        ip = ""
    _wsl_ipv4_cache = ip
    if ip:
        logger.info("WSL Redis target | ipv4=%s", ip)
    elif os.name == "nt":
        logger.warning("WSL Redis IP not found; using Redis URL host as-is")
    return ip


def rewrite_loopback_url_for_wsl(url: str, *, force_discover: bool = False) -> str:
    """On Windows, point loopback Redis URLs at the WSL IP when WSL is present."""
    if not url or os.name != "nt" or not _wsl_rewrite_enabled():
        return url
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    host = (parsed.hostname or "").lower()
    if host not in _LOOPBACK_HOSTS:
        return url
    wsl_ip = discover_wsl_ipv4(force=force_discover)
    if not wsl_ip:
        return url
    auth = ""
    if parsed.username is not None:
        if parsed.password is not None:
            auth = f"{parsed.username}:{parsed.password}@"
        else:
            auth = f"{parsed.username}@"
    port = parsed.port or 6379
    rewritten = urlunparse(parsed._replace(netloc=f"{auth}{wsl_ip}:{port}"))
    if rewritten != url:
        logger.info("Redis URL host %s -> %s (WSL)", host, wsl_ip)
    return rewritten


def _resolve_redis_url() -> str:
    """Return the Redis URL, or empty when production has no Redis configured."""
    global REDIS_URL
    explicit = (os.getenv("REDIS_URL") or REDIS_URL or "").strip()
    if explicit:
        REDIS_URL = explicit
        return rewrite_loopback_url_for_wsl(explicit)
    try:
        from app.config.settings import settings

        configured = (getattr(settings, "redis_url", None) or "").strip()
        app_env = (
            os.getenv("APP_ENV") or getattr(settings, "app_env", "") or "production"
        ).lower()
    except Exception:
        configured = ""
        app_env = os.getenv("APP_ENV", "production").lower()
    if configured:
        REDIS_URL = configured
        return rewrite_loopback_url_for_wsl(configured)
    if app_env in ("production", "prod", "staging"):
        logger.warning("REDIS_URL not set in production — Redis features will be disabled")
        return ""
    REDIS_URL = "redis://127.0.0.1:6379/0"
    return rewrite_loopback_url_for_wsl(REDIS_URL)


def get_redis_client():
    """Return the global async Redis client instance, or None if unavailable.

    Created lazily on the running event loop. Import-time construction binds
    asyncio locks to a different loop on Windows and leaves a stale client
    after Redis was down at boot.
    """
    global redis_client
    if redis_client is None:
        try:
            target_url = _resolve_redis_url()
            if not target_url:
                return None
            redis_client = _create_redis_client(target_url)
        except Exception as exc:
            logger.error("Failed to initialize Redis client: %s", exc)
            redis_client = None
    return redis_client


def get_redis():
    """Backward-compatible alias used by health checks and older call sites."""
    return get_redis_client()


def _redis_available() -> bool:
    """True when a live client can be obtained (recreates after close if possible)."""
    return get_redis_client() is not None


async def close_redis_client() -> None:
    """Dispose the global Redis client (call on app shutdown)."""
    global redis_client
    client = redis_client
    redis_client = None
    # Keep the WSL IP cache: closing a stale socket is not a WSL restart.
    if client is None:
        return
    try:
        aclose = getattr(client, "aclose", None)
        if callable(aclose):
            await aclose()
        else:
            close = getattr(client, "close", None)
            if callable(close):
                result = close()
                if hasattr(result, "__await__"):
                    await result
        logger.info("Redis client closed")
    except Exception as exc:
        logger.warning("Redis client close failed: %s", exc)


class RedisBlocklist:
    @staticmethod
    async def add_token(jti: str, expires_in: int):
        """Add a JWT ID (jti) to the blocklist with an expiration"""
        client = get_redis_client()
        if client is None:
            return
        await client.setex(f"blocklist:{jti}", expires_in, "revoked")

    @staticmethod
    async def is_revoked(jti: str) -> bool:
        """Check if a JWT ID is in the blocklist"""
        client = get_redis_client()
        if client is None:
            return False
        return await client.exists(f"blocklist:{jti}") > 0

class RateLimiter:
    @staticmethod
    async def is_rate_limited(key: str, max_requests: int, window_seconds: int) -> bool:
        """Simple rate limiter using Redis"""
        client = get_redis_client()
        if client is None:
            return False
        current_count = await client.incr(f"ratelimit:{key}")
        if current_count == 1:
            await client.expire(f"ratelimit:{key}", window_seconds)
        
        return current_count > max_requests

    @staticmethod
    async def check_lockout(key: str, max_attempts: int, lockout_minutes: int) -> bool:
        """Lockout after max_attempts. Returns True if locked out."""
        client = get_redis_client()
        if client is None:
            return False
        # This checks if lockout key exists
        locked = await client.exists(f"lockout:{key}")
        if locked:
            return True
            
        attempts = await client.get(f"attempts:{key}")
        if attempts and int(attempts) >= max_attempts:
            # Create lockout key
            await client.setex(f"lockout:{key}", lockout_minutes * 60, "locked")
            await client.delete(f"attempts:{key}")
            return True
        return False

    @staticmethod
    async def increment_attempt(key: str, window_minutes: int = 15):
        """Increment attempt count for a key"""
        client = get_redis_client()
        if client is None:
            return 0
        count = await client.incr(f"attempts:{key}")
        if count == 1:
            await client.expire(f"attempts:{key}", window_minutes * 60)
        return count
    
    @staticmethod
    async def reset_attempts(key: str):
        """Reset attempts after successful login"""
        client = get_redis_client()
        if client is None:
            return
        await client.delete(f"attempts:{key}")
        await client.delete(f"lockout:{key}")
