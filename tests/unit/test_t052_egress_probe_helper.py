"""t052: egress probe helper CLI (runs in the Browser image).

The helper is exercised in-process here (same code path the Supervisor
helper container executes) against controlled local echo/proxy fixtures.
"""

from __future__ import annotations

import http.client
import http.server
import json
import socketserver
import sys
import threading
import types
from pathlib import Path
from urllib.parse import urlparse

import pytest

from cbrowser.runtime_agent.egress_probe import main


class _EchoHandler(http.server.BaseHTTPRequestHandler):
    body = b"203.0.113.7"

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
    def do_GET(self):
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
def proxy_fixture():
    echo = _ThreadingServer(("127.0.0.1", 0), _EchoHandler)
    proxy = _ThreadingServer(("127.0.0.1", 0), _ForwardProxyHandler)
    for srv in (echo, proxy):
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {
        "echo_url": f"http://127.0.0.1:{echo.server_address[1]}/ip",
        "proxy_port": proxy.server_address[1],
    }
    for srv in (echo, proxy):
        srv.shutdown()
        srv.server_close()


@pytest.fixture
def stub_geoip2(monkeypatch, tmp_path):
    mapping = {"203.0.113.7": "JP"}

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


def _credentials_file(tmp_path, proxy_port, password="s3cret-pw"):
    path = tmp_path / "proxy_credentials.json"
    path.write_text(
        json.dumps(
            {
                "scheme": "http",
                "host": "127.0.0.1",
                "port": proxy_port,
                "username": "user",
                "password": password,
                "credential_revision": 1,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_helper_prints_egress_and_country(
    proxy_fixture, stub_geoip2, tmp_path, capsys
):
    creds = _credentials_file(tmp_path, proxy_fixture["proxy_port"])
    rc = main(
        [
            "--credentials-file",
            str(creds),
            "--geoip-db",
            str(stub_geoip2),
            "--echo-url",
            proxy_fixture["echo_url"],
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload == {"egress_ip": "203.0.113.7", "country_code": "JP"}
    # Byte-level: the password never appears in the helper's stdout.
    assert b"s3cret-pw" not in out.encode("utf-8")


def test_helper_missing_geoip_db(proxy_fixture, tmp_path, capsys):
    creds = _credentials_file(tmp_path, proxy_fixture["proxy_port"])
    rc = main(
        [
            "--credentials-file",
            str(creds),
            "--geoip-db",
            str(tmp_path / "GeoLite2-City.mmdb"),
            "--echo-url",
            proxy_fixture["echo_url"],
        ]
    )
    assert rc == 1
    assert json.loads(capsys.readouterr().out) == {
        "error_code": "geoip_db_missing"
    }


def test_helper_unreachable_echo(stub_geoip2, tmp_path, capsys):
    creds = _credentials_file(tmp_path, 1)
    rc = main(
        [
            "--credentials-file",
            str(creds),
            "--geoip-db",
            str(stub_geoip2),
            "--echo-url",
            "http://127.0.0.1:1/ip",
            "--timeout",
            "2",
        ]
    )
    assert rc == 1
    assert json.loads(capsys.readouterr().out) == {
        "error_code": "echo_unreachable"
    }


def test_helper_missing_credentials_file(stub_geoip2, tmp_path, capsys):
    rc = main(
        [
            "--credentials-file",
            str(tmp_path / "nope.json"),
            "--geoip-db",
            str(stub_geoip2),
        ]
    )
    assert rc == 1
    assert json.loads(capsys.readouterr().out) == {
        "error_code": "proxy_credentials_unavailable"
    }


def test_helper_malformed_credentials_file(stub_geoip2, tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    rc = main(
        ["--credentials-file", str(bad), "--geoip-db", str(stub_geoip2)]
    )
    assert rc == 1
    assert json.loads(capsys.readouterr().out) == {
        "error_code": "proxy_credentials_unavailable"
    }
