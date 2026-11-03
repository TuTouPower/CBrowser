"""Trusted proxy XFF parsing and two-layer login budgets."""

from __future__ import annotations

import time

import pytest
from cbrowser.auth.client_ip import parse_trusted_proxy_cidrs, resolve_client_ip
from cbrowser.auth.rate_limiter import LoginRateLimiter


def test_xff_is_ignored_without_trusted_proxies() -> None:
    networks = parse_trusted_proxy_cidrs(None)
    assert resolve_client_ip("198.51.100.5", "203.0.113.9", networks) == "198.51.100.5"


def test_leftmost_untrusted_hop_is_selected_from_the_right() -> None:
    networks = parse_trusted_proxy_cidrs("10.0.0.0/8,127.0.0.1/32")
    assert (
        resolve_client_ip(
            "127.0.0.1", "203.0.113.9, 10.0.0.7, 10.0.0.8", networks
        )
        == "203.0.113.9"
    )
    assert resolve_client_ip("10.0.0.2", "203.0.113.9", networks) == "203.0.113.9"
    # A spoofed leftmost value is kept only when everything else is trusted.
    assert (
        resolve_client_ip("10.0.0.2", "198.51.100.1, 203.0.113.9", networks)
        == "203.0.113.9"
    )


def test_untrusted_peer_cannot_spoof_xff() -> None:
    networks = parse_trusted_proxy_cidrs("10.0.0.0/8")
    assert (
        resolve_client_ip("198.51.100.5", "203.0.113.9", networks) == "198.51.100.5"
    )


def test_malformed_trusted_cidr_is_rejected() -> None:
    with pytest.raises(ValueError, match="trusted proxy CIDR"):
        parse_trusted_proxy_cidrs("not-a-cidr")


def test_per_source_window_and_global_budget() -> None:
    now = [1000.0]
    limiter = LoginRateLimiter(
        max_failures=2,
        window_seconds=60,
        global_max_failures=3,
        global_window_seconds=900,
        clock=lambda: now[0],
    )
    limiter.record_failure("a")
    limiter.record_failure("a")
    assert limiter.rate_limit_layer("a") == "source"
    assert limiter.retry_after_seconds("a") > 0
    assert limiter.rate_limit_layer("b") is None
    now[0] += 61
    assert limiter.rate_limit_layer("a") is None
    limiter.record_failure("c")
    limiter.record_failure("c")
    assert limiter.rate_limit_layer("c") == "source"
    assert limiter.rate_limit_layer("d") == "global"
    assert limiter.retry_after_seconds("d") > 0
