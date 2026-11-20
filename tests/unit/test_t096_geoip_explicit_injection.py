"""t096: explicit GeoIP injection and resource-class probe failures.

The production runner must receive its GeoIpLookup at construction; no
hidden ``CBROWSER_GEOIP_*`` environment read may decide the database path
behind the probe I/O. These tests exercise the real path judgement in
``GeoIpLookup`` (only geoip2's ``Reader`` is faked), not a stub lookup.
"""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path

import pytest

from cbrowser.api.runtime_coordinator import RuntimeCoordinator
from cbrowser.domain.proxy_endpoint import ProxyEndpoint
from cbrowser.services.egress_probe import InProcessEgressProbeRunner
from cbrowser.shared.egress import (
    EgressProbeError,
    GeoIpLookup,
    resolve_geoip_db_path,
)
from tests.unit.test_t052_egress_observation import echo_pair  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.yaml"


@pytest.fixture
def real_mmdb(monkeypatch, tmp_path) -> Path:
    """A real on-disk mmdb path with only geoip2's Reader faked.

    Path judgement (``db_path.is_file()``) stays real; the Reader returns
    full country/city names so ``GeoIpLookup.location`` is exercised end
    to end (t096 AC-005).
    """

    class FakeCountry:
        iso_code = "JP"
        name = "Japan"

    class FakeInnerCity:
        name = "Tokyo"

    class FakeResponse:
        country = FakeCountry()
        city = FakeInnerCity()

    class FakeReader:
        def __init__(self, path):
            assert Path(path).is_file()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def city(self, ip):
            assert ip == "203.0.113.7"
            return FakeResponse()

    database_mod = types.ModuleType("geoip2.database")
    database_mod.Reader = FakeReader
    geoip2_mod = types.ModuleType("geoip2")
    geoip2_mod.database = database_mod
    monkeypatch.setitem(sys.modules, "geoip2", geoip2_mod)
    monkeypatch.setitem(sys.modules, "geoip2.database", database_mod)
    path = tmp_path / "geoip" / "GeoLite2-City.mmdb"
    path.parent.mkdir()
    path.write_bytes(b"fake-mmdb")
    return path


def _proxied_endpoint(pair: dict) -> ProxyEndpoint:
    port = int(pair["proxy_url"].rsplit(":", 1)[1])
    return ProxyEndpoint(
        scheme="http", host="127.0.0.1", port=port, username="user", password="pw"
    )


def _probe(pair: dict, runner: InProcessEgressProbeRunner):
    return runner.probe("px-1", _proxied_endpoint(pair), 1)


@pytest.mark.asyncio
async def test_runner_requires_explicit_geoip_at_construction() -> None:
    with pytest.raises(TypeError):
        InProcessEgressProbeRunner()


def test_geoip_lookup_never_reads_hidden_env(monkeypatch, real_mmdb) -> None:
    monkeypatch.setenv("CBROWSER_GEOIP_DB", str(real_mmdb))
    assert GeoIpLookup().db_path is None


@pytest.mark.asyncio
async def test_unconfigured_path_is_resource_failure_even_when_env_has_db(
    monkeypatch, echo_pair, real_mmdb
) -> None:
    # A hidden env var points at a real mmdb; it must NOT rescue a runner
    # whose caller failed to inject a path (t096 AC-002).
    monkeypatch.setenv("CBROWSER_GEOIP_DB", str(real_mmdb))
    runner = InProcessEgressProbeRunner(
        geoip=GeoIpLookup(),
        echo_urls=(echo_pair["proxied_url"],),
        map_loopback=False,
    )
    with pytest.raises(EgressProbeError) as exc:
        await _probe(echo_pair, runner)
    assert exc.value.code == "geoip_db_missing"


@pytest.mark.asyncio
async def test_injected_real_mmdb_path_completes_geoip_lookup(
    echo_pair, real_mmdb
) -> None:
    runner = InProcessEgressProbeRunner(
        geoip=GeoIpLookup(db_path=real_mmdb),
        echo_urls=(echo_pair["proxied_url"],),
        map_loopback=False,
    )
    result = await _probe(echo_pair, runner)
    assert result.egress_ip == "203.0.113.7"
    assert result.country_code == "JP"
    assert result.country_name == "Japan"
    assert result.city == "Tokyo"


def test_resolve_geoip_db_path_reads_cache_env(monkeypatch) -> None:
    monkeypatch.delenv("CBROWSER_GEOIP_DB", raising=False)
    monkeypatch.setenv("CBROWSER_GEOIP_CACHE", "/data/engine-cache/geoip")
    assert resolve_geoip_db_path() == Path(
        "/data/engine-cache/geoip/GeoLite2-City.mmdb"
    )


def test_coordinator_injects_resolved_path_into_runner(monkeypatch) -> None:
    monkeypatch.setenv("CBROWSER_GEOIP_CACHE", "/data/engine-cache/geoip")
    coord = RuntimeCoordinator(
        supervisor_url=None,
        supervisor_token=None,
        profile_service=object(),
        geoip_db_path=resolve_geoip_db_path(),
    )
    runner = coord.egress_probe_runner()
    assert runner._geoip.db_path == Path(
        "/data/engine-cache/geoip/GeoLite2-City.mmdb"
    )


def _service_environment(text: str, service: str) -> str:
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l == f"  {service}:")
    end = next(
        (i for i in range(start + 1, len(lines)) if re.match(r"^  \w+:\s*$", lines[i])),
        len(lines),
    )
    block = lines[start:end]
    env_start = next(i for i, l in enumerate(block) if l.strip() == "environment:")
    out: list[str] = []
    for line in block[env_start + 1 :]:
        if line.strip() == "" or line.startswith("      "):
            out.append(line)
        else:
            break
    return "\n".join(out)


def test_compose_api_declares_geoip_cache_like_supervisor() -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    api_env = _service_environment(text, "api")
    sup_env = _service_environment(text, "supervisor")
    cache_line = r"^\s+CBROWSER_GEOIP_CACHE:\s*.+/engine-cache/geoip\s*$"
    assert re.search(cache_line, api_env, re.M)
    assert re.search(cache_line, sup_env, re.M)
