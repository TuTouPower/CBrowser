"""t052: proxy link API + egress observation (integration, real app).

Drives the real FastAPI app (TestClient) with a LocalEgressProbeRunner
backed by controlled local echo/proxy fixtures, so the probe path is
exercised end to end without Docker.  The production runner is the
Supervisor one; this file only proves the API/service contract.
"""

from __future__ import annotations

import http.client
import http.server
import socketserver
import sys
import threading
import time
import types
from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from api_auth import create_auth_context
from cbrowser.api.app import create_app
from cbrowser.api.v1.deps import get_profile_service
from cbrowser.domain.egress_observation import EgressProbeError, GeoIpLookup
from cbrowser.services.egress_probe import (
    EgressProbeResult,
    LocalEgressProbeRunner,
)


# ---- controlled echo + forward proxy (same shape as the unit fixtures) -----


class _EchoHandler(http.server.BaseHTTPRequestHandler):
    body = b"198.51.100.1"

    def do_GET(self):
        data = self.body
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class _ForwardProxyHandler(http.server.BaseHTTPRequestHandler):
    seen: list[str] = []

    def do_GET(self):
        type(self).seen.append(self.path)
        target = urlparse(self.path)
        conn = http.client.HTTPConnection(target.hostname, target.port or 80, timeout=5)
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

    def log_message(self, *args):
        pass


class _ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


@pytest.fixture(scope="module")
def echo_fixtures():
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
        "proxy_port": proxy.server_address[1],
        "proxy_seen": _ForwardProxyHandler.seen,
    }
    for srv in (direct, proxied, proxy):
        srv.shutdown()
        srv.server_close()


@pytest.fixture(autouse=True)
def stub_geoip2(monkeypatch, tmp_path):
    """Fake geoip2.database: 203.0.113.7 -> JP, 198.51.100.1 -> US."""
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


class _BlockingRunner:
    """Probe runner that waits on a threading.Event before delegating.

    Lets the test observe the pending observation between the save and
    the probe result (AC-007 invalidation is visible, not just eventual).
    """

    def __init__(self, delegate, gate: threading.Event):
        self._delegate = delegate
        self._gate = gate

    async def probe(self, proxy_id, endpoint, credential_revision):
        await __import__("asyncio").to_thread(self._gate.wait, 30.0)
        return await self._delegate.probe(proxy_id, endpoint, credential_revision)


@pytest.fixture
def app_client(tmp_path: Path, echo_fixtures, stub_geoip2):
    ctx = create_auth_context(tmp_path)
    app = create_app(
        db_path=tmp_path / "t052.db",
        admin_password_file=ctx.admin_password_file,
        artifacts_root=tmp_path / "artifacts",
    )
    gate = threading.Event()
    gate.set()
    runner = LocalEgressProbeRunner(
        geoip=GeoIpLookup(db_path=stub_geoip2),
        echo_urls=[echo_fixtures["proxied_url"]],
    )
    blocking = _BlockingRunner(runner, gate)
    with TestClient(app, base_url=ctx.allowed_origin) as client:
        login = client.post(
            "/api/v1/auth/login", json={"password": ctx.admin_password}
        )
        assert login.status_code == 200
        headers = {
            "X-CSRF-Token": login.json()["csrf_token"],
            "Origin": ctx.allowed_origin,
        }
        service = app.dependency_overrides[get_profile_service]()
        service.set_egress_probe_runner(blocking)
        yield client, headers, echo_fixtures, gate, service


def _wait_for(client, headers, proxy_id, status, timeout=15.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/api/v1/proxies/{proxy_id}", headers=headers).json()
        if last["observation_status"] == status:
            return last
        time.sleep(0.05)
    raise AssertionError(f"proxy {proxy_id} never reached {status}: {last}")


def _create(client, headers, payload):
    resp = client.post("/api/v1/proxies", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---- AC-002: four link formats --------------------------------------------


@pytest.mark.parametrize(
    "link,expected",
    [
        (
            "http://user:p%40ss@proxy.example.com:8080",
            {"scheme": "http", "host": "proxy.example.com", "port": 8080,
             "username": "user", "has_password": True,
             "proxy_url": "http://user@proxy.example.com:8080"},
        ),
        (
            "proxy.example.com:8080",
            {"scheme": "http", "host": "proxy.example.com", "port": 8080,
             "username": None, "has_password": False,
             "proxy_url": "http://proxy.example.com:8080"},
        ),
        (
            "proxy.example.com:8080:user:p:ss",
            {"scheme": "http", "host": "proxy.example.com", "port": 8080,
             "username": "user", "has_password": True,
             "proxy_url": "http://user@proxy.example.com:8080"},
        ),
        (
            "user:p%40ss@proxy.example.com:8080",
            {"scheme": "http", "host": "proxy.example.com", "port": 8080,
             "username": "user", "has_password": True,
             "proxy_url": "http://user@proxy.example.com:8080"},
        ),
        (
            "socks5://user:pass@[2001:db8::1]:1080",
            {"scheme": "socks5", "host": "2001:db8::1", "port": 1080,
             "username": "user", "has_password": True,
             "proxy_url": "socks5://user@[2001:db8::1]:1080"},
        ),
    ],
)
def test_create_accepts_all_four_link_formats(app_client, link, expected):
    client, headers, _fx, _gate, _svc = app_client
    body = _create(client, headers, {"proxy_url": link})
    for key, value in expected.items():
        assert body[key] == value, (key, body)
    assert "password" not in body
    assert "s3cret" not in str(body) and "p@ss" not in str(body)
    # test f001: the redacted link must equal the expected value — the
    # old `body["proxy_url"] == body["proxy_url"]` was a tautology.
    assert body["proxy_url"] == expected["proxy_url"]
    assert "p@ss" not in body["proxy_url"] and "p:ss" not in body["proxy_url"]


@pytest.mark.parametrize(
    "payload",
    [
        {"proxy_url": "ftp://proxy.example.com:8080"},
        {"proxy_url": "proxy.example.com:0"},
        {"proxy_url": ""},
        # flat fields are no longer a valid entry shape (t052 link-only)
        {"name": "p", "scheme": "http", "host": "h", "port": 8080},
        # country_code is no longer writable
        {"proxy_url": "http://h:8080", "country_code": "US"},
    ],
)
def test_create_rejects_invalid_links_and_flat_fields(app_client, payload):
    client, headers, _fx, _gate, _svc = app_client
    resp = client.post("/api/v1/proxies", json=payload, headers=headers)
    assert resp.status_code == 422, resp.text


# ---- AC-004/AC-005: secrecy + name derivation ------------------------------


def test_password_never_leaks_into_any_response(app_client):
    client, headers, _fx, _gate, _svc = app_client
    created = _create(
        client, headers, {"proxy_url": "http://user:never-show@proxy.example.com:8080"}
    )
    assert "never-show" not in created["proxy_url"]
    for url in (
        f"/api/v1/proxies/{created['id']}",
        "/api/v1/proxies",
    ):
        resp = client.get(url, headers=headers)
        assert resp.status_code == 200
        assert "never-show" not in resp.text
        # test f002: the old conditional collapsed to `assert True` for
        # the list response — check every item unconditionally.
        payload = resp.json()
        if isinstance(payload, dict):
            assert "password" not in payload
        else:
            assert isinstance(payload, list)
            assert all("password" not in item for item in payload)
    patched = client.patch(
        f"/api/v1/proxies/{created['id']}",
        json={"proxy_url": "http://user:rotated-secret@proxy.example.com:8080"},
        headers=headers,
    )
    assert patched.status_code == 200
    assert "rotated-secret" not in patched.text
    probed = client.post(
        f"/api/v1/proxies/{created['id']}/probe", headers=headers
    )
    assert probed.status_code == 200
    assert "rotated-secret" not in probed.text


def test_name_defaults_to_host_port_and_manual_name_survives(app_client):
    client, headers, _fx, _gate, _svc = app_client
    created = _create(client, headers, {"proxy_url": "proxy.example.com:8080"})
    assert created["name"] == "proxy.example.com:8080"
    renamed = client.patch(
        f"/api/v1/proxies/{created['id']}",
        json={"name": "My Proxy"},
        headers=headers,
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "My Proxy"
    relinked = client.patch(
        f"/api/v1/proxies/{created['id']}",
        json={"proxy_url": "proxy.example.com:9090"},
        headers=headers,
    )
    assert relinked.status_code == 200
    assert relinked.json()["name"] == "My Proxy"
    assert relinked.json()["port"] == 9090


# ---- AC-006/AC-007/AC-008: auto-probe, invalidation, proxy perspective -----


def test_create_auto_probes_and_observes_proxy_egress(app_client):
    client, headers, fx, _gate, _svc = app_client
    port = fx["proxy_port"]
    created = _create(
        client, headers, {"proxy_url": f"http://user:pw@127.0.0.1:{port}"}
    )
    observed = _wait_for(client, headers, created["id"], "ok")
    assert observed["egress_ip"] == "203.0.113.7"  # proxy egress, not API egress
    assert observed["country_code"] == "JP"
    assert observed["observed_at"] is not None


def test_endpoint_change_invalidates_old_observation(app_client):
    client, headers, fx, gate, _svc = app_client
    port = fx["proxy_port"]
    gate.clear()  # hold probes at the gate so "pending" is observable
    try:
        created = _create(
            client, headers, {"proxy_url": f"http://user:pw@127.0.0.1:{port}"}
        )
        pending = client.get(
            f"/api/v1/proxies/{created['id']}", headers=headers
        ).json()
        assert pending["observation_status"] == "pending"
        assert pending["country_code"] is None
        gate.set()
        observed = _wait_for(client, headers, created["id"], "ok")
        assert observed["country_code"] == "JP"

        # Change the endpoint: the old country must disappear at once.
        gate.clear()
        patched = client.patch(
            f"/api/v1/proxies/{created['id']}",
            json={"proxy_url": f"http://user:pw@127.0.0.1:{port}"},
            headers=headers,
        )
        assert patched.status_code == 200
        invalidated = client.get(
            f"/api/v1/proxies/{created['id']}", headers=headers
        ).json()
        assert invalidated["observation_status"] == "pending"
        assert invalidated["country_code"] is None
        gate.set()
        observed = _wait_for(client, headers, created["id"], "ok")
        assert observed["country_code"] == "JP"

        # Password rotation (same endpoint, new password) also invalidates.
        gate.clear()
        rotated = client.patch(
            f"/api/v1/proxies/{created['id']}",
            json={"proxy_url": f"http://user:newpw@127.0.0.1:{port}"},
            headers=headers,
        )
        assert rotated.status_code == 200
        invalidated = client.get(
            f"/api/v1/proxies/{created['id']}", headers=headers
        ).json()
        assert invalidated["observation_status"] == "pending"
        assert invalidated["country_code"] is None
        gate.set()
        _wait_for(client, headers, created["id"], "ok")
    finally:
        gate.set()


# ---- AC-006 failure path (code f002) ---------------------------------------


class _ExplodingRunner:
    """Runner that fails with a non-EgressProbeError, as the Supervisor
    runner did on a non-dict JSON body (AttributeError)."""

    async def probe(self, proxy_id, endpoint, credential_revision):
        raise AttributeError("'list' object has no attribute 'get'")


def test_probe_runner_unexpected_error_records_failed_not_500(app_client):
    client, headers, _fx, _gate, svc = app_client
    svc.set_egress_probe_runner(_ExplodingRunner())
    created = _create(client, headers, {"proxy_url": "proxy.example.com:8080"})
    # Manual probe: the unexpected runner error must become a failed
    # observation (HTTP 200), never a 500 with the pending row hanging.
    resp = client.post(
        f"/api/v1/proxies/{created['id']}/probe", headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["observation_status"] == "failed"
    assert resp.json()["country_code"] is None


# ---- AC-009: probe accepts only the proxy id -------------------------------


def test_probe_rejects_bodies_that_try_to_redirect_credentials(app_client):
    client, headers, fx, _gate, _svc = app_client
    port = fx["proxy_port"]
    created = _create(
        client, headers, {"proxy_url": f"http://user:pw@127.0.0.1:{port}"}
    )
    for body in (
        {"host": "evil.example.com"},
        {"host": "127.0.0.1", "port": 9999, "scheme": "http"},
        {"proxy_url": "http://evil.example.com:8080"},
        {"username": "someone-else"},
    ):
        resp = client.post(
            f"/api/v1/proxies/{created['id']}/probe", json=body, headers=headers
        )
        assert resp.status_code == 422, (body, resp.text)
    # The stored endpoint is what gets probed, not the rejected body.
    observed = client.post(
        f"/api/v1/proxies/{created['id']}/probe", headers=headers
    )
    assert observed.status_code == 200
    assert observed.json()["egress_ip"] == "203.0.113.7"


def test_probe_missing_proxy_is_404(app_client):
    client, headers, _fx, _gate, _svc = app_client
    resp = client.post("/api/v1/proxies/nope/probe", headers=headers)
    assert resp.status_code == 404


def test_probe_failure_records_failed_observation_not_a_guess(app_client):
    client, headers, fx, _gate, service = app_client

    class _FailingRunner:
        async def probe(self, proxy_id, endpoint, credential_revision):
            raise EgressProbeError("echo_unreachable", "no echo service responded")

    service.set_egress_probe_runner(_FailingRunner())
    created = _create(
        client, headers, {"proxy_url": "http://user:pw@127.0.0.1:9999"}
    )
    observed = _wait_for(client, headers, created["id"], "failed")
    assert observed["country_code"] is None
    assert observed["egress_ip"] is None
