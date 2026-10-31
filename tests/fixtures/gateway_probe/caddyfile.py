"""Caddyfile template generator for CBrowser Gateway E2E tests."""

from __future__ import annotations


def generate_caddyfile(api_ip: str, gateway_ip: str) -> str:
    """Generates internal TLS Caddy config routing API, Gateway and static client."""
    return f"""{{
    admin off
    auto_https disable_redirects
    default_sni 127.0.0.1
}}

https://127.0.0.1 {{
    tls internal

    handle /api/* {{
        reverse_proxy http://{api_ip}:8000
    }}

    handle /stream/* {{
        reverse_proxy http://{gateway_ip}:18097
    }}

    handle {{
        root * /var/www/html
        try_files {{path}} /index.html
        file_server
    }}
}}
"""
