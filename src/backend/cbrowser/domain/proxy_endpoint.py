"""Proxy endpoint value object + proxy-link parser (t052).

A proxy link is the *only* entry representation for a proxy endpoint.
The endpoint is a value object: ``scheme`` / ``host`` / ``port`` /
``username`` plus a write-only secret (``password``).  The fingerprint is
derived from scheme/host/port/username only, so a password rotation does
not change the endpoint identity while a host/port/username change does.

Four link formats are accepted (see :func:`parse_proxy_link`):

1. standard URL ``scheme://user:pass@host:port``
2. schemeless ``host:port`` (defaults to ``http``)
3. ``host:port:user:pass``
4. ``user:pass@host:port``

IPv6 hosts must be bracketed (``[2001:db8::1]:8080``).  The password never
appears in ``repr``/``str``, in the redacted link, or in the fingerprint.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import quote, unquote

PROXY_SCHEMES = ("http", "https", "socks5")

#: Hostname the Supervisor substitutes for a loopback endpoint so a
#: containerised Browser/probe helper can reach a proxy that only listens
#: on the host's loopback interface.  The container is given
#: ``extra_hosts={"host.docker.internal": "host-gateway"}`` for this.
HOST_GATEWAY_HOSTNAME = "host.docker.internal"

_LOOPBACK_NETWORKS = (ipaddress.ip_network("127.0.0.0/8"),)
_PERCENT_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")


class ProxyLinkError(ValueError):
    """Field-level link parse failure (``field`` is always ``proxy_url``)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.field = "proxy_url"


def _fail(code: str, message: str) -> None:
    raise ProxyLinkError(code, message)


def _percent_decode(value: str) -> str:
    """Percent-decode userinfo, rejecting malformed escapes.

    ``urllib.parse.unquote`` silently keeps bad escapes; a bad escape is a
    user error here (it usually means an unencoded ``%`` in the password),
    so validate first.
    """
    stripped = re.sub(r"%[0-9A-Fa-f]{2}", "", value)
    if "%" in stripped:
        _fail("malformed_percent_encoding", "malformed percent-encoding in credentials")
    return unquote(value)


def _normalize_host(raw_host: str, bracketed: bool) -> str:
    if not raw_host:
        _fail("missing_host", "missing host")
    if any(ch in raw_host for ch in (" ", "\t", "\n", "\r", "[", "]", "/", "?", "#", "@")):
        _fail("invalid_host", "invalid host")
    if bracketed:
        try:
            return ipaddress.IPv6Address(raw_host).compressed
        except ValueError:
            _fail("invalid_host", "invalid IPv6 host")
    if ":" in raw_host:
        _fail("invalid_host", "invalid host")
    try:
        return ipaddress.ip_address(raw_host).compressed
    except ValueError:
        return raw_host.lower()


def _parse_port(port_text: str) -> int:
    if not re.fullmatch(r"\d+", port_text or ""):
        _fail("invalid_port", "invalid port")
    port = int(port_text)
    if not 1 <= port <= 65535:
        _fail("port_out_of_range", "port out of range")
    return port


def _split_host_port(text: str) -> tuple[str, int]:
    """Split ``host:port`` / ``[v6]:port``; returns the normalized host."""
    if text.startswith("["):
        close = text.find("]")
        if close == -1:
            _fail("unclosed_ipv6_bracket", "unclosed IPv6 bracket")
        host = _normalize_host(text[1:close], bracketed=True)
        after = text[close + 1 :]
        if not after.startswith(":"):
            _fail("missing_port", "missing port")
        return host, _parse_port(after[1:])
    colon = text.rfind(":")
    if colon == -1:
        _fail("missing_port", "missing port")
    host = _normalize_host(text[:colon], bracketed=False)
    return host, _parse_port(text[colon + 1 :])


def _split_userinfo(userinfo: str) -> tuple[str | None, str | None]:
    if not userinfo:
        return None, None
    colon = userinfo.find(":")
    if colon == -1:
        username = _percent_decode(userinfo)
        return (username or None), None
    username = _percent_decode(userinfo[:colon])
    password = _percent_decode(userinfo[colon + 1 :])
    return (username or None), (password or None)


def _parse_url_form(raw: str) -> ProxyEndpoint:
    match = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*):\/\/(.*)$", raw, re.DOTALL)
    assert match is not None  # caller checked for "://"
    scheme = match.group(1).lower()
    if scheme not in PROXY_SCHEMES:
        _fail("unsupported_scheme", f"unsupported scheme: {scheme}")
    rest = match.group(2)
    authority_end = len(rest)
    for sep in ("/", "?", "#"):
        idx = rest.find(sep)
        if idx != -1:
            authority_end = min(authority_end, idx)
    authority = rest[:authority_end]
    if not authority:
        _fail("missing_host", "missing host")
    at_count = authority.count("@")
    if at_count > 1:
        _fail("multiple_at_signs", "multiple @ in authority")
    userinfo = ""
    hostport = authority
    if at_count == 1:
        at = authority.index("@")
        userinfo = authority[:at]
        hostport = authority[at + 1 :]
    username, password = _split_userinfo(userinfo)
    host, port = _split_host_port(hostport)
    return ProxyEndpoint(
        scheme=scheme, host=host, port=port, username=username, password=password
    )


def _parse_schemeless(raw: str) -> ProxyEndpoint:
    # Format 4 (user:pass@host:port): the part after the single "@" must
    # itself parse as host:port, otherwise fall through to formats 2/3
    # (so a "@" inside a format-3 password does not misroute parsing).
    if "@" in raw:
        at = raw.rfind("@")
        left, right = raw[:at], raw[at + 1 :]
        if ":" in right and "@" not in left:
            try:
                host, port = _split_host_port(right)
            except ProxyLinkError:
                host = port = None  # type: ignore[assignment]
            if host is not None:
                username, password = _split_userinfo(left)
                return ProxyEndpoint(
                    scheme="http",
                    host=host,
                    port=port,  # type: ignore[arg-type]
                    username=username,
                    password=password,
                )
    if raw.startswith("["):
        close = raw.find("]")
        if close == -1:
            _fail("unclosed_ipv6_bracket", "unclosed IPv6 bracket")
        host = _normalize_host(raw[1:close], bracketed=True)
        after = raw[close + 1 :]
        if not after.startswith(":"):
            _fail("missing_port", "missing port")
        rest = after[1:]
        parts = rest.split(":", 1)
        port = _parse_port(parts[0])
        if len(parts) == 1:
            return ProxyEndpoint(scheme="http", host=host, port=port)
        userinfo = parts[1]
        username, password = _split_userinfo(userinfo)
        return ProxyEndpoint(
            scheme="http", host=host, port=port, username=username, password=password
        )
    parts = raw.split(":")
    if len(parts) == 2:
        host, port = _split_host_port(raw)
        return ProxyEndpoint(scheme="http", host=host, port=port)
    if len(parts) >= 4 and re.fullmatch(r"\d+", parts[1]):
        host = _normalize_host(parts[0], bracketed=False)
        port = _parse_port(parts[1])
        username, password = _split_userinfo(":".join(parts[2:]))
        return ProxyEndpoint(
            scheme="http", host=host, port=port, username=username, password=password
        )
    _fail("ambiguous_format", "unrecognised proxy link format")


@dataclass(frozen=True)
class ProxyEndpoint:
    """A proxy endpoint value object.  The password is write-only: it is
    excluded from ``repr``/``str``, from the redacted link and from the
    fingerprint, and must never be logged."""

    scheme: str
    host: str
    port: int
    username: str | None = None
    password: str | None = None

    def __post_init__(self) -> None:
        if self.scheme not in PROXY_SCHEMES:
            raise ProxyLinkError("unsupported_scheme", f"unsupported scheme: {self.scheme}")
        if not 1 <= self.port <= 65535:
            raise ProxyLinkError("port_out_of_range", "port out of range")
        if self.username is not None and self.password is not None:
            pass
        elif self.password is not None and self.username is None:
            raise ProxyLinkError(
                "invalid_credentials", "password without username"
            )

    def __repr__(self) -> str:
        return f"ProxyEndpoint({self.redacted_link()!r})"

    def __str__(self) -> str:
        return self.redacted_link()

    @property
    def fingerprint(self) -> str:
        """Endpoint identity: scheme/host/port/username, never the password."""
        material = "\0".join(
            [self.scheme, self.host, str(self.port), self.username or ""]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @property
    def is_loopback(self) -> bool:
        return is_loopback_host(self.host)

    @property
    def mapped_host(self) -> str:
        """Host as seen from inside a container: loopback endpoints are
        rewritten to the host gateway; everything else is unchanged."""
        return map_loopback_host(self.host)

    def display_name(self) -> str:
        """Default proxy name: ``host:port`` (IPv6 bracketed)."""
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"{host}:{self.port}"

    def redacted_link(self) -> str:
        """Link safe for display, state and logs: no password, ever."""
        host = f"[{self.host}]" if ":" in self.host else self.host
        if self.username is not None:
            return (
                f"{self.scheme}://{quote(self.username, safe='')}@{host}:{self.port}"
            )
        return f"{self.scheme}://{host}:{self.port}"

    def proxy_url(self) -> str:
        """Full link with percent-encoded credentials, for httpx/Chromium
        use only.  Never store, display or log this value."""
        host = f"[{self.host}]" if ":" in self.host else self.host
        if self.username is not None:
            userinfo = quote(self.username, safe="")
            if self.password is not None:
                userinfo += f":{quote(self.password, safe='')}"
            return f"{self.scheme}://{userinfo}@{host}:{self.port}"
        return f"{self.scheme}://{host}:{self.port}"

    def as_credentials_dict(self) -> dict[str, object]:
        """Plain mapping for the internal credentials hand-off (API ->
        Supervisor / runtime).  The caller owns secrecy of the result."""
        return {
            "scheme": self.scheme,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
        }


def is_loopback_host(host: str) -> bool:
    """True for ``127.0.0.0/8``, ``localhost`` and ``::1``."""
    lowered = host.strip().lower()
    if lowered in ("localhost", "localhost."):
        return True
    try:
        ip = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv4Address):
        return ip in _LOOPBACK_NETWORKS[0]
    return ip == ipaddress.IPv6Address("::1")


def map_loopback_host(host: str) -> str:
    """Map a loopback host to the host-gateway hostname containers use;
    non-loopback hosts pass through unchanged."""
    return HOST_GATEWAY_HOSTNAME if is_loopback_host(host) else host


def map_endpoint_for_container(endpoint: ProxyEndpoint) -> ProxyEndpoint:
    """Rewrite a loopback endpoint for container use (t052 AC-010/AC-011).

    The stored endpoint keeps its loopback host (fingerprint-stable); the
    runtime copy handed to a Browser/probe container uses the host-gateway
    hostname, and the container is given
    ``extra_hosts={"host.docker.internal": "host-gateway"}`` so the name
    resolves to the host.  Non-loopback endpoints pass through unchanged.
    """
    if not endpoint.is_loopback:
        return endpoint
    return ProxyEndpoint(
        scheme=endpoint.scheme,
        host=HOST_GATEWAY_HOSTNAME,
        port=endpoint.port,
        username=endpoint.username,
        password=endpoint.password,
    )


def parse_proxy_link(raw: str) -> ProxyEndpoint:
    """Parse one of the four accepted proxy-link formats.

    Raises :class:`ProxyLinkError` with a machine-readable ``code`` for
    invalid input; the input is never echoed back in the message.
    """
    if not isinstance(raw, str) or not raw.strip():
        _fail("empty_input", "empty proxy url")
    text = raw.strip()
    if "://" in text:
        return _parse_url_form(text)
    return _parse_schemeless(text)
