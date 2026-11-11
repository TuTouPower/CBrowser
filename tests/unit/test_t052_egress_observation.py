"""t052: egress observation — echo fetch, local GeoIP, validity rules.

The probe path is exercised against a controlled local forward proxy +
controlled echo fixtures (AC-008): a direct echo returns the API egress
IP, the proxied echo returns the proxy egress IP, and the observation
must carry the proxy one.
"""

from __future__ import annotations

import datetime
import http.client
import http.server
import socketserver
import sys
import threading
import types
from pathlib import Path

import pytest

from cbrowser.domain.egress_observation import (
    EgressObservation,
    EgressProbeError,
    GeoIpLookup,
    GeoIpUnavailableError,
    fetch_egress_ip,
    observation_is_current,
    probe_egress,
)
from cbrowser.domain.proxy_endpoint import parse_proxy_link


def _utc(*args, **kwargs):
    return datetime.datetime(*args, **kwargs, tzinfo=datetime.timezone.utc)


def _obs(**overrides):
    base = dict(
        proxy_id="px-1",
        endpoint_fingerprint="fp",
        credential_revision=3,
        perspective="browser",
        egress_ip="203.0.113.7",
        country_code="JP",
        source="supervisor_probe",
        status="ok",
        error_code=None,
        observed_at=_utc(2026, 11, 11, 10, 0, 0),
        expires_at=_utc(2026, 11, 12, 10, 0, 0),
    )
    base.update(overrides)
    return EgressObservation(**base)


def test_observation_current_when_matching_and_fresh():
    assert observation_is_current(
        _obs(), "fp", 3, _utc(2026, 11, 11, 12, 0, 0)
    )


@pytest.mark.parametrize(
    "overrides,fingerprint,revision,now",
    [
        ({"status": "failed"}, "fp", 3, _utc(2026, 11, 11, 12, 0, 0)),
        ({"status": "pending"}, "fp", 3, _utc(2026, 11, 11, 12, 0, 0)),
        ({"endpoint_fingerprint": "other"}, "fp", 3, _utc(2026, 11, 11, 12, 0, 0)),
        ({"credential_revision": 4}, "fp", 3, _utc(2026, 11, 11, 12, 0, 0)),
        ({"country_code": None}, "fp", 3, _utc(2026, 11, 11, 12, 0, 0)),
        ({"egress_ip": None}, "fp", 3, _utc(2026, 11, 11, 12, 0, 0)),
        ({}, "fp", 3, _utc(2026, 11, 12, 10, 0, 1)),  # expired
    ],
)
def test_observation_not_current(overrides, fingerprint, revision, now):
    assert not observation_is_current(_obs(**overrides), fingerprint, revision, now)


def test_observation_without_expiry_never_expires():
    assert observation_is_current(
        _obs(expires_at=None), "fp", 3, _utc(2027, 1, 1)
    )


# ---- GeoIP lookup (geoip2 stubbed; no real mmdb on this machine) ----------


@pytest.fixture
def stub_geoip2(monkeypatch, tmp_path):
    """Install a fake ``geoip2.database`` whose Reader maps fixed IPs."""
    mapping = {"203.0.113.7": "JP", "198.51.100.1": "US"}

    class FakeCountry:
        def __init__(self, code):
            self.iso_code = code

    class FakeCity:
        def __init__(self, code):
            self.country = FakeCountry(code)

    class FakeReader:
        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def city(self, ip):
            return FakeCity(mapping[ip])

    database_mod = types.ModuleType("geoip2.database")
    database_mod.Reader = FakeReader
    geoip2_mod = types.ModuleType("geoip2")
    geoip2_mod.database = database_mod
    monkeypatch.setitem(sys.modules, "geoip2", geoip2_mod)
    monkeypatch.setitem(sys.modules, "geoip2.database", database_mod)
    db_path = tmp_path / "GeoLite2-City.mmdb"
    db_path.write_bytes(b"fake-mmdb")
    return db_path


def test_geoip_lookup_returns_country(stub_geoip2):
    lookup = GeoIpLookup(db_path=stub_geoip2)
    assert lookup.country_code("203.0.113.7") == "JP"
    assert lookup.country_code("198.51.100.1") == "US"


def test_geoip_lookup_missing_db_file(tmp_path):
    lookup = GeoIpLookup(db_path=tmp_path / "GeoLite2-City.mmdb")
    with pytest.raises(GeoIpUnavailableError) as excinfo:
        lookup.country_code("203.0.113.7")
    assert excinfo.value.code == "geoip_db_missing"


def test_geoip_lookup_missing_geoip2_package(monkeypatch, tmp_path):
    monkeypatch.delitem(sys.modules, "geoip2", raising=False)
    monkeypatch.delitem(sys.modules, "geoip2.database", raising=False)
    db_path = tmp_path / "GeoLite2-City.mmdb"
    db_path.write_bytes(b"fake-mmdb")
    lookup = GeoIpLookup(db_path=db_path)
    with pytest.raises(GeoIpUnavailableError) as excinfo:
        lookup.country_code("203.0.113.7")
    assert excinfo.value.code == "geoip2_missing"


# ---- controlled echo + forward-proxy fixtures ------------------------------


class _EchoHandler(http.server.BaseHTTPRequestHandler):
    body = b"198.51.100.1"

    def do_GET(self):
        data = self.body
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # silence
        pass


class _ForwardProxyHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP forward proxy: relays absolute-form GETs, records them."""

    seen: list[str] = []

    def do_GET(self):
        type(self).seen.append(self.path)
        from urllib.parse import urlparse

        target = urlparse(self.path)
        conn = http.client.HTTPConnection(
            target.hostname, target.port or 80, timeout=5
        )
        try:
            conn.request("GET", target.path or "/", headers={"Host": target.netloc})
            resp = conn.getresponse()
            data = resp.read()
        finally:
            conn.close()
        self.send_response(resp.status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # silence
        pass


class _ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


@pytest.fixture
def echo_pair():
    """Direct echo (API egress) + proxied echo (proxy egress) + proxy."""
    direct_handler = type("H", (_EchoHandler,), {"body": b"198.51.100.1"})
    direct = _ThreadingServer(("127.0.0.1", 0), direct_handler)

    proxied_handler = type("H", (_EchoHandler,), {"body": b"203.0.113.7"})
    proxied = _ThreadingServer(("127.0.0.1", 0), proxied_handler)

    _ForwardProxyHandler.seen = []
    proxy = _ThreadingServer(("127.0.0.1", 0), _ForwardProxyHandler)

    threads = [
        threading.Thread(target=srv.serve_forever, daemon=True)
        for srv in (direct, proxied, proxy)
    ]
    for t in threads:
        t.start()
    yield {
        "direct_url": f"http://127.0.0.1:{direct.server_address[1]}/ip",
        "proxied_url": f"http://127.0.0.1:{proxied.server_address[1]}/ip",
        "proxy_url": f"http://127.0.0.1:{proxy.server_address[1]}",
        "proxy_seen": _ForwardProxyHandler.seen,
    }
    for srv in (direct, proxied, proxy):
        srv.shutdown()
        srv.server_close()


def test_fetch_egress_ip_direct(echo_pair):
    ip = fetch_egress_ip(None, [echo_pair["direct_url"]])
    assert ip == "198.51.100.1"


def test_fetch_egress_ip_through_proxy_uses_proxy_egress(echo_pair):
    """AC-008: the observed IP is the proxy egress, never the API egress."""
    endpoint = parse_proxy_link(
        f"http://127.0.0.1:{echo_pair['proxy_url'].rsplit(':', 1)[1]}"
    )
    ip = fetch_egress_ip(endpoint.proxy_url(), [echo_pair["proxied_url"]])
    assert ip == "203.0.113.7"
    assert ip != "198.51.100.1"
    assert len(echo_pair["proxy_seen"]) == 1
    assert echo_pair["proxy_seen"][0].startswith("http://127.0.0.1:")


def test_fetch_egress_ip_unreachable_echo(echo_pair):
    with pytest.raises(EgressProbeError) as excinfo:
        fetch_egress_ip(None, ["http://127.0.0.1:1/ip"], timeout=2.0)
    assert excinfo.value.code == "echo_unreachable"


def test_fetch_egress_ip_invalid_body(echo_pair):
    class BadHandler(_EchoHandler):
        body = b"not-an-ip"

    bad = _ThreadingServer(("127.0.0.1", 0), BadHandler)
    t = threading.Thread(target=bad.serve_forever, daemon=True)
    t.start()
    try:
        with pytest.raises(EgressProbeError) as excinfo:
            fetch_egress_ip(
                None, [f"http://127.0.0.1:{bad.server_address[1]}/ip"]
            )
        assert excinfo.value.code == "invalid_echo_response"
    finally:
        bad.shutdown()
        bad.server_close()


def test_probe_egress_returns_ip_and_country(echo_pair, stub_geoip2):
    endpoint = parse_proxy_link(
        f"http://127.0.0.1:{echo_pair['proxy_url'].rsplit(':', 1)[1]}"
    )
    lookup = GeoIpLookup(db_path=stub_geoip2)
    egress_ip, country = probe_egress(
        endpoint,
        echo_urls=[echo_pair["proxied_url"]],
        geoip=lookup,
    )
    assert egress_ip == "203.0.113.7"
    assert country == "JP"


def test_probe_egress_geoip_missing_is_failed_not_guessed(
    echo_pair, tmp_path
):
    endpoint = parse_proxy_link(
        f"http://127.0.0.1:{echo_pair['proxy_url'].rsplit(':', 1)[1]}"
    )
    lookup = GeoIpLookup(db_path=tmp_path / "GeoLite2-City.mmdb")
    with pytest.raises(EgressProbeError) as excinfo:
        probe_egress(
            endpoint,
            echo_urls=[echo_pair["proxied_url"]],
            geoip=lookup,
        )
    assert excinfo.value.code == "geoip_db_missing"
