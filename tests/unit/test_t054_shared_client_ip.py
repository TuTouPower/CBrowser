"""t054 A14: client_ip has exactly one implementation, shared by API and Gateway.

The two byte-identical copies (``cbrowser.auth.client_ip`` and
``cbrowser.gateway.client_ip``) are deleted; both sides import
``cbrowser.shared.client_ip``. The Gateway image includes the shared
module through its Dockerfile file whitelist (see
test_docker_build_contexts.py).
"""

from __future__ import annotations

import importlib

import pytest

from cbrowser.shared.client_ip import (
    parse_trusted_proxy_cidrs,
    resolve_client_ip,
)


def test_duplicate_client_ip_modules_are_gone() -> None:
    for name in ("cbrowser.auth.client_ip", "cbrowser.gateway.client_ip"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(name)


def test_api_and_gateway_import_the_shared_module() -> None:
    import cbrowser.api.app as app_module
    import cbrowser.api.v1.auth_router as auth_router
    import cbrowser.api.v1.control_router as control_router
    import cbrowser.gateway.server as gateway_server

    assert app_module.parse_trusted_proxy_cidrs.__module__ == (
        "cbrowser.shared.client_ip"
    )
    for module in (auth_router, control_router):
        assert module.resolve_client_ip.__module__ == (
            "cbrowser.shared.client_ip"
        )
    assert gateway_server.resolve_client_ip.__module__ == (
        "cbrowser.shared.client_ip"
    )
    assert gateway_server.parse_trusted_proxy_cidrs.__module__ == (
        "cbrowser.shared.client_ip"
    )


def test_no_module_imports_the_old_copies() -> None:
    # automation_router imports resolve_client_ip lazily inside a
    # function, so its import is asserted on source, not on the module
    # attribute.
    import inspect

    import cbrowser.api.v1.automation_router as automation_router

    source = inspect.getsource(automation_router)
    assert "from cbrowser.shared.client_ip import resolve_client_ip" in source
    assert "auth.client_ip" not in source
    assert "gateway.client_ip" not in source


def test_xff_is_ignored_without_trusted_proxies() -> None:
    networks = parse_trusted_proxy_cidrs(None)
    assert resolve_client_ip("198.51.100.5", "203.0.113.9", networks) == (
        "198.51.100.5"
    )


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


def test_peer_none_resolves_to_unknown() -> None:
    """t054 R1 test f003: a missing peer has no trustworthy source."""
    networks = parse_trusted_proxy_cidrs("172.18.0.0/16")
    assert resolve_client_ip(None, "203.0.113.9", networks) == "unknown"


def test_malformed_xff_hop_is_skipped() -> None:
    """t054 R1 test f003: an unparsable XFF hop is skipped, the remaining
    leftmost untrusted hop wins; a chain of only malformed hops falls
    back to the peer."""
    networks = parse_trusted_proxy_cidrs("10.0.0.0/8,127.0.0.1/32")
    assert (
        resolve_client_ip(
            "127.0.0.1", "203.0.113.9, not-an-ip, 10.0.0.7", networks
        )
        == "203.0.113.9"
    )
    assert resolve_client_ip("127.0.0.1", "not-an-ip", networks) == "127.0.0.1"


def test_untrusted_peer_xff_is_not_trusted() -> None:
    networks = parse_trusted_proxy_cidrs("172.18.0.0/16")
    # The peer is outside the trusted edge subnet: XFF must be ignored,
    # so two different XFF senders behind one untrusted peer stay one source.
    assert resolve_client_ip("198.51.100.5", "203.0.113.9", networks) == (
        "198.51.100.5"
    )
    assert resolve_client_ip("198.51.100.5", "198.51.100.6", networks) == (
        "198.51.100.5"
    )
