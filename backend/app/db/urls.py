"""Helpers that expose database targets without credentials."""
from __future__ import annotations

from urllib.parse import urlsplit

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def public_db_target(url: str | None) -> str:
    """Host/path only. Never returns userinfo, query, or fragment."""
    raw = (url or "").strip()
    if not raw:
        return "(unset)"
    try:
        if "@" in raw:
            return raw.split("@", 1)[-1].split("?", 1)[0].split("#", 1)[0]
        parsed = urlsplit(raw)
        host = parsed.netloc or parsed.path
        return (host or "(unparsed)").split("?", 1)[0]
    except Exception:
        return "(unparsed)"


def postgres_hostname(url: str | None) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw.replace("postgresql+asyncpg://", "postgresql://", 1))
        if parsed.hostname:
            return parsed.hostname.lower()
        if "@" in raw:
            hostport = raw.split("@", 1)[-1].split("/", 1)[0]
            return hostport.split(":")[0].lower()
    except Exception:
        return ""
    return ""


def is_local_postgres_url(url: str | None) -> bool:
    host = postgres_hostname(url)
    return host in _LOCAL_HOSTS
