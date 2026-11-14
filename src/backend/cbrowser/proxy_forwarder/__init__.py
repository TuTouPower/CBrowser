"""Credentialless proxy auth-forwarder (t065).

The Browser container must never see proxy credentials: its argv, /proc,
environment, logs and every readable mount are visible to Chromium. The
forwarder is a third container that owns the secret instead. It exposes a
credentialless local entry point on the Browser network and injects the
upstream authentication itself:

- HTTP/HTTPS upstreams: the forwarder speaks the HTTP proxy protocol,
  adding ``Proxy-Authorization``; CONNECT tunnels HTTPS, absolute-form
  requests are forwarded as one request per connection.
- SOCKS5 upstreams: the forwarder speaks SOCKS5 with username/password
  auth and passes the target hostname through as a domain address, so DNS
  happens at the upstream (remote DNS) and never locally.

Failure is always closed: an unreachable upstream, a 407, a SOCKS5 auth
failure or any malformed client request closes the client connection with
no response body. The forwarder never attempts a direct connection to the
origin, and the Browser network policy (which allows only the forwarder
endpoint) makes a direct fallback impossible even if Chromium tried one.

Stdlib only: this package is copied into the minimal forwarder image,
which carries no third-party dependencies.
"""

from __future__ import annotations

from .forwarder import (
    PROXY_FORWARDER_FILENAME,
    PROXY_FORWARDER_PORT,
    ForwarderConfigError,
    UpstreamConfig,
    load_upstream_config,
    read_forwarder_endpoint,
    serve,
)

__all__ = [
    "PROXY_FORWARDER_FILENAME",
    "PROXY_FORWARDER_PORT",
    "ForwarderConfigError",
    "UpstreamConfig",
    "load_upstream_config",
    "read_forwarder_endpoint",
    "serve",
]
