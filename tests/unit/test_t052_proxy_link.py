"""t052: ProxyEndpoint value object + proxy-link parser (TDD, red first).

Four link formats, IPv6, special-character passwords, fingerprinting,
redaction and loopback mapping.  The parser is the single source of truth
for link entry; the frontend parser must stay behaviour-compatible.
"""

import pytest

from cbrowser.domain.proxy_endpoint import (
    ProxyEndpoint,
    ProxyLinkError,
    is_loopback_host,
    map_loopback_host,
    parse_proxy_link,
)


@pytest.mark.parametrize(
    "link,expected",
    [
        (
            "http://user:p%40ss@proxy.example.com:8080",
            ("http", "proxy.example.com", 8080, "user", "p@ss"),
        ),
        (
            "socks5://proxy.example.com:1080",
            ("socks5", "proxy.example.com", 1080, None, None),
        ),
        (
            "https://user@proxy.example.com:8443",
            ("https", "proxy.example.com", 8443, "user", None),
        ),
        ("HTTP://PROXY.EXAMPLE.COM:8080", ("http", "proxy.example.com", 8080, None, None)),
        # format 2: schemeless host:port defaults to http
        ("proxy.example.com:8080", ("http", "proxy.example.com", 8080, None, None)),
        # format 3: host:port:user:pass (password may contain ':')
        (
            "proxy.example.com:8080:user:p:ss",
            ("http", "proxy.example.com", 8080, "user", "p:ss"),
        ),
        # format 4: user:pass@host:port
        (
            "user:p%40ss@proxy.example.com:8080",
            ("http", "proxy.example.com", 8080, "user", "p@ss"),
        ),
        ("user@proxy.example.com:8080", ("http", "proxy.example.com", 8080, "user", None)),
        # IPv6 in every format
        (
            "http://user:pass@[2001:db8::1]:8080",
            ("http", "2001:db8::1", 8080, "user", "pass"),
        ),
        ("[2001:db8::1]:8080", ("http", "2001:db8::1", 8080, None, None)),
        (
            "[2001:db8::1]:8080:user:pass",
            ("http", "2001:db8::1", 8080, "user", "pass"),
        ),
        (
            "user:pass@[2001:db8::1]:8080",
            ("http", "2001:db8::1", 8080, "user", "pass"),
        ),
        # loopback links parse like any other endpoint
        ("http://127.0.0.1:7890", ("http", "127.0.0.1", 7890, None, None)),
        ("http://user:pass@localhost:7890", ("http", "localhost", 7890, "user", "pass")),
        ("http://user:pass@[::1]:7890", ("http", "::1", 7890, "user", "pass")),
        # trailing path/query/fragment are ignored (old parseProxyUrl behaviour)
        (
            "http://user:pass@proxy.example.com:8080/some/path?x=1#frag",
            ("http", "proxy.example.com", 8080, "user", "pass"),
        ),
        # port boundaries
        ("proxy.example.com:1", ("http", "proxy.example.com", 1, None, None)),
        ("proxy.example.com:65535", ("http", "proxy.example.com", 65535, None, None)),
    ],
)
def test_parse_proxy_link_valid(link, expected):
    endpoint = parse_proxy_link(link)
    assert (
        endpoint.scheme,
        endpoint.host,
        endpoint.port,
        endpoint.username,
        endpoint.password,
    ) == expected


@pytest.mark.parametrize(
    "link",
    [
        "",
        "   ",
        "proxy.example.com",  # no port
        "proxy.example.com:0",
        "proxy.example.com:65536",
        "proxy.example.com:notaport",
        "ftp://proxy.example.com:8080",  # unsupported scheme
        "http://proxy.example.com",  # URL form without port
        "http://user:pass@proxy.example.com:8080@evil.example.com:1",  # double @
        "http://user:%zz@proxy.example.com:8080",  # bad percent-encoding
        "http://[2001:db8::1:8080",  # unclosed IPv6 bracket
        "http://[2001:db8::1]",  # bracketed IPv6 without port
        "2001:db8::1:8080",  # bare IPv6 without brackets is ambiguous
        "proxy.example.com:8080:user",  # 3-part schemeless is ambiguous
        "http://proxy .example.com:8080",  # space in host
        "http:///proxy.example.com:8080",  # empty host in URL form
    ],
)
def test_parse_proxy_link_invalid(link):
    with pytest.raises(ProxyLinkError):
        parse_proxy_link(link)


def test_parse_errors_carry_field_level_code():
    with pytest.raises(ProxyLinkError) as excinfo:
        parse_proxy_link("ftp://proxy.example.com:8080")
    assert excinfo.value.code == "unsupported_scheme"
    assert excinfo.value.field == "proxy_url"
    with pytest.raises(ProxyLinkError) as excinfo:
        parse_proxy_link("proxy.example.com:0")
    assert excinfo.value.code == "port_out_of_range"


def test_fingerprint_excludes_password_and_is_stable():
    a = parse_proxy_link("http://user:secret1@proxy.example.com:8080")
    b = parse_proxy_link("http://user:other-secret@proxy.example.com:8080")
    c = parse_proxy_link("http://user:secret1@proxy.example.com:8080")
    assert a.fingerprint == b.fingerprint
    assert a.fingerprint == c.fingerprint
    assert len(a.fingerprint) == 64
    d = parse_proxy_link("http://other:secret1@proxy.example.com:8080")
    assert d.fingerprint != a.fingerprint
    e = parse_proxy_link("http://user:secret1@proxy.example.com:9090")
    assert e.fingerprint != a.fingerprint


def test_redacted_link_never_contains_password():
    endpoint = parse_proxy_link("http://user:s3cret@proxy.example.com:8080")
    redacted = endpoint.redacted_link()
    assert "s3cret" not in redacted
    assert redacted == "http://user@proxy.example.com:8080"
    bare = parse_proxy_link("proxy.example.com:8080")
    assert bare.redacted_link() == "http://proxy.example.com:8080"
    v6 = parse_proxy_link("http://user:s3cret@[2001:db8::1]:8080")
    assert v6.redacted_link() == "http://user@[2001:db8::1]:8080"
    assert "s3cret" not in v6.redacted_link()


def test_proxy_url_round_trips_through_parser():
    # The full URL (with credentials) must parse back to the same endpoint,
    # so the value the Browser/helper receives is exactly what was entered.
    original = parse_proxy_link("socks5://user:p%40ss:word@[2001:db8::1]:1080")
    reparsed = parse_proxy_link(original.proxy_url())
    assert reparsed == original


def test_password_never_in_repr_or_str():
    endpoint = parse_proxy_link("http://user:s3cret@proxy.example.com:8080")
    assert "s3cret" not in repr(endpoint)
    assert "s3cret" not in str(endpoint)


def test_display_name_derivation():
    assert parse_proxy_link("proxy.example.com:8080").display_name() == (
        "proxy.example.com:8080"
    )
    assert parse_proxy_link("http://user:p@[2001:db8::1]:8080").display_name() == (
        "[2001:db8::1]:8080"
    )


@pytest.mark.parametrize(
    "host,expected",
    [
        ("127.0.0.1", True),
        ("127.0.0.2", True),
        ("127.255.255.255", True),
        ("localhost", True),
        ("LOCALHOST", True),
        ("::1", True),
        ("192.168.1.1", False),
        ("10.0.0.1", False),
        ("proxy.example.com", False),
        ("2001:db8::1", False),
    ],
)
def test_is_loopback_host(host, expected):
    assert is_loopback_host(host) is expected


def test_map_loopback_host():
    assert map_loopback_host("127.0.0.1") == "host.docker.internal"
    assert map_loopback_host("localhost") == "host.docker.internal"
    assert map_loopback_host("::1") == "host.docker.internal"
    assert map_loopback_host("proxy.example.com") == "proxy.example.com"


def test_endpoint_mapped_host_property():
    assert parse_proxy_link("http://127.0.0.1:7890").mapped_host == (
        "host.docker.internal"
    )
    assert parse_proxy_link("http://proxy.example.com:8080").mapped_host == (
        "proxy.example.com"
    )


def test_endpoint_is_immutable_value_object():
    endpoint = parse_proxy_link("proxy.example.com:8080")
    assert isinstance(endpoint, ProxyEndpoint)
    with pytest.raises(AttributeError):
        endpoint.port = 9090  # type: ignore[misc]
