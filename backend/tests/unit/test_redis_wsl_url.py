"""Windows + WSL Redis URL rewrite: redis-py cannot use the localhost relay."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import app.core.redis as redis_mod


def setup_function() -> None:
    redis_mod.reset_wsl_ipv4_cache()


def teardown_function() -> None:
    redis_mod.reset_wsl_ipv4_cache()


def test_rewrite_loopback_to_wsl_ip_on_windows(monkeypatch):
    monkeypatch.setattr(redis_mod.os, "name", "nt")
    monkeypatch.setenv("REDIS_WSL_REWRITE", "1")
    monkeypatch.setattr(redis_mod, "discover_wsl_ipv4", lambda force=False: "172.19.248.171")

    assert (
        redis_mod.rewrite_loopback_url_for_wsl("redis://127.0.0.1:6379/0")
        == "redis://172.19.248.171:6379/0"
    )
    assert (
        redis_mod.rewrite_loopback_url_for_wsl("redis://localhost:6379/1")
        == "redis://172.19.248.171:6379/1"
    )
    assert (
        redis_mod.rewrite_loopback_url_for_wsl("redis://:secret@127.0.0.1:6379/0")
        == "redis://:secret@172.19.248.171:6379/0"
    )


def test_rewrite_leaves_remote_hosts_alone(monkeypatch):
    monkeypatch.setattr(redis_mod.os, "name", "nt")
    monkeypatch.setattr(redis_mod, "discover_wsl_ipv4", lambda force=False: "172.19.248.171")
    remote = "redis://red-abc.upstash.io:6379/0"
    assert redis_mod.rewrite_loopback_url_for_wsl(remote) == remote


def test_rewrite_opt_out(monkeypatch):
    monkeypatch.setattr(redis_mod.os, "name", "nt")
    monkeypatch.setenv("REDIS_WSL_REWRITE", "0")
    monkeypatch.setattr(redis_mod, "discover_wsl_ipv4", lambda force=False: "172.19.248.171")
    loopback = "redis://127.0.0.1:6379/0"
    assert redis_mod.rewrite_loopback_url_for_wsl(loopback) == loopback


def test_rewrite_noop_without_wsl_ip(monkeypatch):
    monkeypatch.setattr(redis_mod.os, "name", "nt")
    monkeypatch.setattr(redis_mod, "discover_wsl_ipv4", lambda force=False: "")
    loopback = "redis://127.0.0.1:6379/0"
    assert redis_mod.rewrite_loopback_url_for_wsl(loopback) == loopback


def test_rewrite_noop_on_non_windows(monkeypatch):
    monkeypatch.setattr(redis_mod.os, "name", "posix")
    monkeypatch.setattr(redis_mod, "discover_wsl_ipv4", lambda force=False: "172.19.248.171")
    loopback = "redis://127.0.0.1:6379/0"
    assert redis_mod.rewrite_loopback_url_for_wsl(loopback) == loopback


def test_discover_wsl_ipv4_parses_hostname_i(monkeypatch):
    monkeypatch.setattr(redis_mod.os, "name", "nt")
    completed = MagicMock()
    completed.stdout = "172.19.248.171 fd00::1 \n"
    with patch.object(redis_mod.subprocess, "run", return_value=completed) as run:
        assert redis_mod.discover_wsl_ipv4(force=True) == "172.19.248.171"
        run.assert_called_once()
        assert redis_mod.discover_wsl_ipv4() == "172.19.248.171"
        assert run.call_count == 1  # cached


def test_resolve_redis_url_rewrites_explicit_loopback(monkeypatch):
    monkeypatch.setattr(redis_mod.os, "name", "nt")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setenv("REDIS_WSL_REWRITE", "1")
    monkeypatch.setattr(redis_mod, "discover_wsl_ipv4", lambda force=False: "172.19.248.171")
    assert redis_mod._resolve_redis_url() == "redis://172.19.248.171:6379/0"


@pytest.mark.asyncio
async def test_close_redis_client_keeps_wsl_ip_cache(monkeypatch):
    monkeypatch.setattr(redis_mod.os, "name", "nt")
    redis_mod._wsl_ipv4_cache = "172.19.248.171"
    redis_mod.redis_client = None
    await redis_mod.close_redis_client()
    assert redis_mod._wsl_ipv4_cache == "172.19.248.171"
