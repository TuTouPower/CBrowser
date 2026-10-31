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

    reverse_proxy /api/* http://{api_ip}:8000
    reverse_proxy /stream/* http://{gateway_ip}:18097

    root * /var/www/html
    file_server
}}
"""
