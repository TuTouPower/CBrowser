"""t064: the rendered Caddyfile carries the edge authorization contract.

The viewer handshake crosses three parties (browser, Caddy, Gateway)
with the API as resolver; the Caddyfile is the one artifact that wires
them together, so its security-relevant directives are pinned here:
internal paths refused externally, forged authorization headers deleted
at the edge, forward_auth resolution for the signal route only, and the
session cookie stripped before the Gateway.
"""

from __future__ import annotations

from cbrowser.network_config import generate_caddyfile


def _block(content: str, header: str) -> str:
    start = content.index(header)
    end = content.index("\n    }", start)
    return content[start:end]


def test_internal_api_paths_are_refused_before_the_api_proxy() -> None:
    content = generate_caddyfile(56661)
    internal = _block(content, "handle /api/v1/internal/*")
    assert "respond 404" in internal
    assert content.index("handle /api/v1/internal/*") < content.index(
        "handle /api/*"
    )


def test_signal_route_resolves_at_the_edge_and_strips_the_cookie() -> None:
    content = generate_caddyfile(56661)
    signal = _block(content, "handle /stream/*/signal {")
    # The route wrapper is load-bearing: Caddy's default directive
    # order runs forward_auth before request_header, which would delete
    # the API-issued context immediately after it is copied in. Inside
    # route, declaration order is execution order.
    assert "route {" in signal
    assert signal.index("request_header -X-CBrowser-Viewer-Grant") < signal.index(
        "forward_auth"
    )
    assert signal.index("forward_auth") < signal.index("reverse_proxy")
    # Client-forged authorization context is deleted before resolution.
    assert "request_header -X-CBrowser-Authorized-Profile" in signal
    assert "request_header -X-CBrowser-Viewer-Grant" in signal
    # Resolution happens at the API with the edge proof; only the
    # placeholder is rendered, never a secret value.
    assert "forward_auth http://api:8000" in signal
    assert "uri /api/v1/internal/edge/viewer-authorize" in signal
    assert 'header_up X-CBrowser-Edge-Proof "{env.CBROWSER_EDGE_PROOF_SECRET}"' in signal
    assert (
        "copy_headers X-CBrowser-Authorized-Profile X-CBrowser-Viewer-Grant"
        in signal
    )
    # The Gateway never receives the session cookie on this route.
    assert "reverse_proxy http://gateway:18080" in signal
    assert "header_up -Cookie" in signal
    # The signal route is more specific than the plain stream proxy and
    # must be rendered (and therefore evaluated) first.
    assert content.index("handle /stream/*/signal {") < content.index(
        "handle /stream/* {"
    )


def test_agent_register_route_keeps_the_plain_stream_proxy() -> None:
    content = generate_caddyfile(56661)
    plain = _block(content, "handle /stream/* {")
    assert "reverse_proxy http://gateway:18080" in plain
    assert "forward_auth" not in plain
    assert "header_up -Cookie" not in plain


def test_rendering_stays_deterministic_and_secret_free() -> None:
    first = generate_caddyfile(56661)
    assert generate_caddyfile(56661) == first
    assert "{env.CBROWSER_EDGE_PROOF_SECRET}" in first
