"""Deploy-time network configuration: deterministic Caddyfile generation and Origin derivation.

The network configuration is a deploy-time input, not a runtime setting
(t054, ADR 031): the HTTPS port comes from the deployment environment
(``CBROWSER_HTTPS_PORT``), the Caddyfile is rendered once by deploy.sh,
and API + Gateway derive the Origin whitelist from the same port. There
is no runtime apply path, no LAN mode, and no on-disk applied-state file
beyond the Caddyfile itself. The Caddyfile always binds loopback only.
"""

from __future__ import annotations

import hashlib

DEFAULT_HTTPS_PORT = 56661
CADDYFILE_FILENAME = "Caddyfile"


def _validate_port(https_port: int) -> int:
    if type(https_port) is not int or not 1 <= https_port <= 65535:
        raise ValueError(f"https_port must be an integer between 1 and 65535, got {https_port!r}")
    return https_port


def _format_origin(host: str, port: int, scheme: str = "https") -> str:
    """Format scheme://host[:port], omitting default ports (https/443, http/80).

    Keeps parity with request-side ``normalize_origin`` which strips default
    ports, so whitelist entries compare equal without caller changes.
    """
    default_port = 443 if scheme == "https" else 80
    if port == default_port:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def derive_origin_whitelist(https_port: int) -> list[str]:
    """Derive allowed origin URLs strictly from the deployment HTTPS port.

    Only loopback hosts are ever allowed (HTTPS only). The port is the
    single deployment input; API and Gateway call this with the same
    value, so their whitelists cannot drift.
    """
    port = _validate_port(https_port)
    return [
        _format_origin("127.0.0.1", port),
        _format_origin("localhost", port),
    ]


def generate_caddyfile(
    https_port: int,
    api_upstream: str = "http://api:8000",
    gateway_upstream: str = "http://gateway:18080",
    frontend_dir: str = "/var/www/html",
) -> str:
    """Deterministically generate the Caddyfile for the deployment port.

    Loopback only: the site addresses are 127.0.0.1/localhost, the
    default SNI is 127.0.0.1, and no other bind host exists. The output
    depends only on its inputs, so the same port always renders the same
    file and the deploy fingerprint (hash of this product) is stable.
    The header records the deployment port the file was rendered for:
    the host port mapping lives in compose, so without it two deploys
    differing only by port would render identical files and the
    fingerprint would not change with the port (AC-006).
    """
    _validate_port(https_port)
    caddyfile = f"""# CBrowser deploy Caddyfile — https_port {https_port} (rendered by deploy.sh; do not edit)
{{
    admin off
    auto_https disable_redirects
    default_sni 127.0.0.1
}}

https://127.0.0.1, https://localhost {{
    tls internal

    handle /api/* {{
        reverse_proxy {api_upstream}
    }}

    handle /stream/* {{
        reverse_proxy {gateway_upstream}
    }}

    handle {{
        root * {frontend_dir}
        try_files {{path}} /index.html
        file_server
    }}
}}
"""
    return caddyfile


def compute_caddyfile_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
