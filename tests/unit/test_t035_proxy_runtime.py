"""t035 AC-007 / AC-008 / AC-010 runtime unit proofs.

Static/unit assertions for the proxy launch argument, the fail-closed paths on
missing/stale proxy credentials, the internal credentials RPC, and the browser
version observation helpers. No Docker container is required.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.domain.models import ConfigVersionSnapshot, ProfileConfig

from cbrowser.api.internal_supervisor import get_proxy_credentials
from cbrowser.runtime_agent.runner import (
    PROXY_CREDENTIALS_CHANGED,
    ProxyCredentialsChangedError as RunnerProxyChanged,
    resolve_proxy_server_arg,
)
from cbrowser.supervisor.core import (
    PROXY_CREDENTIALS_CHANGED as SUP_PROXY_CHANGED,
    ProxyCredentialsChangedError as SupervisorProxyChanged,
    SupervisorCore,
)
from cbrowser.supervisor.docker_adapter import proxy_endpoint_from_credentials

CREDS = {
    "scheme": "socks5",
    "host": "proxy.example.com",
    "port": 1080,
    "username": "user",
    "password": "s3cr3t",
    "credential_revision": 2,
}


def _config(proxy_id: str | None) -> ProfileConfig:
    return ProfileConfig(name="p1", proxy_id=proxy_id)


def _snapshot(revision: int | None) -> ConfigVersionSnapshot:
    return ConfigVersionSnapshot(
        id="snap_1",
        profile_id="p1",
        version=1,
        config={},
        proxy_credential_revision=revision,
        created_at="2026-01-01T00:00:00+00:00",
    )


def _write_creds(path: Path, **overrides) -> None:
    data = dict(CREDS)
    data.update(overrides)
    path.write_text(json.dumps(data), encoding="utf-8")
    path.chmod(0o600)


def _core_with_response(payload: dict, status: int = 200) -> SupervisorCore:
    transport = httpx.MockTransport(
        lambda _req: httpx.Response(status, json=payload)
    )
    api = httpx.AsyncClient(transport=transport, base_url="http://api")
    core = SupervisorCore.__new__(SupervisorCore)
    core.api = api
    core._token_file = None
    return core


# ---- Runner fail-closed paths (AC-007) -----------------------------------
# NOTE (t065): the four build_proxy_server_arg tests that asserted an
# inline-credential --proxy-server argument, and
# test_matching_revision_returns_proxy_arg, were deleted wholesale here:
# t065 removes inline credentials entirely — the Runner now reads only
# the credentialless forwarder endpoint file. The new behaviour is
# covered by tests/unit/test_t065_proxy_forwarder_mounts.py
# (test_runner_resolves_credentialless_forwarder_arg and
# test_runner_fails_closed_on_endpoint_problems). The remaining tests
# below still prove the fail-closed paths on a missing/malformed file.


def test_no_proxy_id_never_injects_proxy(tmp_path: Path) -> None:
    assert (
        resolve_proxy_server_arg(
            _config(None), _snapshot(None), tmp_path / "missing.json"
        )
        is None
    )


def test_missing_credentials_file_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(RunnerProxyChanged) as exc:
        resolve_proxy_server_arg(
            _config("px1"), _snapshot(2), tmp_path / "proxy_credentials.json"
        )
    assert str(exc.value) == PROXY_CREDENTIALS_CHANGED


def test_corrupt_credentials_file_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "proxy_credentials.json"
    path.write_text("not-json", encoding="utf-8")
    with pytest.raises(RunnerProxyChanged):
        resolve_proxy_server_arg(_config("px1"), _snapshot(2), path)


# ---- Supervisor fail-closed paths (AC-007) --------------------------------


async def test_supervisor_revision_mismatch_fails_closed() -> None:
    core = _core_with_response(
        {
            "scheme": "socks5",
            "host": "h",
            "port": 1080,
            "username": "u",
            "password": "pw",
            "credential_revision": 5,
            "proxy_credential_revision": 2,
        }
    )
    with pytest.raises(SupervisorProxyChanged) as exc:
        await core._resolve_proxy_credentials("p1", _config("px1"), 1)
    assert str(exc.value) == SUP_PROXY_CHANGED
    assert "pw" not in str(exc.value)
    await core.api.aclose()


async def test_supervisor_matching_revision_returns_credentials() -> None:
    core = _core_with_response(
        {
            "scheme": "socks5",
            "host": "h",
            "port": 1080,
            "username": "u",
            "password": "pw",
            "credential_revision": 2,
            "proxy_credential_revision": 2,
        }
    )
    data = await core._resolve_proxy_credentials("p1", _config("px1"), 1)
    assert data["password"] == "pw"
    assert data["credential_revision"] == 2
    assert data["proxy_credential_revision"] == 2
    await core.api.aclose()


async def test_supervisor_no_proxy_skips_rpc() -> None:
    core = _core_with_response({})
    assert await core._resolve_proxy_credentials("p1", _config(None), 1) is None
    await core.api.aclose()


async def test_supervisor_missing_proxy_fails_closed() -> None:
    core = _core_with_response({}, status=404)
    with pytest.raises(SupervisorProxyChanged):
        await core._resolve_proxy_credentials("p1", _config("px1"), 1)
    await core.api.aclose()


# ---- Internal credentials RPC (AC-007) -----------------------------------


async def test_internal_credentials_endpoint_returns_secret_and_frozen_revision(
    tmp_path: Path,
) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    from cbrowser.adapters.database.models import (
        Base,
        ProfileConfigVersionModel,
        ProfileModel,
        ProxyModel,
    )

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(
            ProxyModel(
                id="px1",
                name="proxy",
                scheme="socks5",
                host="proxy.example.com",
                port=1080,
                username="user",
                password="s3cr3t",
                credential_revision=7,
            )
        )
        session.add(
            ProfileModel(
                display_number=1,
                id="p1",
                name="p1",
                fingerprint_seed=123456,
                user_data_dir=f"/data/profiles/p1/profile",
                proxy_id="px1",
            )
        )
        session.add(
            ProfileConfigVersionModel(
                id="v1",
                profile_id="p1",
                version=3,
                snapshot=json.dumps(
                    {
                        "config": {"proxy_id": "px1"},
                        "proxy_credential_revision": 4,
                    }
                ),
            )
        )
        await session.commit()
    from cbrowser.adapters.database.repository import ProfileRepository
    from cbrowser.services.profile_service import ProfileService

    service = ProfileService(ProfileRepository(maker))
    result = await get_proxy_credentials("px1", "p1", 3, service)
    assert result.password == "s3cr3t"
    assert result.credential_revision == 7
    assert result.proxy_credential_revision == 4
    await engine.dispose()


# ---- Network egress proxy resolution -------------------------------------


def test_proxy_endpoint_from_credentials(tmp_path: Path) -> None:
    path = tmp_path / "proxy_credentials.json"
    _write_creds(path, host="10.2.3.4", port=1080)
    assert proxy_endpoint_from_credentials(path) == "socks5://10.2.3.4:1080"


def test_proxy_endpoint_absent_when_no_credentials(tmp_path: Path) -> None:
    assert proxy_endpoint_from_credentials(tmp_path / "missing.json") is None


# ---- Browser version observation (AC-010) --------------------------------


async def test_browser_version_is_read_from_cdp_session() -> None:
    from cbrowser.runtime_agent.runner import BrowserRunner

    class FakeSession:
        async def send(self, _method: str) -> dict:
            return {"product": "Chrome/146.0.0.0", "userAgent": "Mozilla/5.0"}

        async def detach(self) -> None:
            return None

    class FakeContext:
        pages = ["page"]

        async def new_cdp_session(self, _page) -> FakeSession:
            return FakeSession()

    runner = BrowserRunner.__new__(BrowserRunner)
    runner.browser_context = FakeContext()
    product, user_agent = await runner._resolve_browser_version()
    assert product == "Chrome/146.0.0.0"
    assert user_agent == "Mozilla/5.0"


def test_read_browser_version_from_runner_info(tmp_path: Path) -> None:
    from cbrowser.supervisor.core import SupervisorCore

    runtime_dir = tmp_path
    (runtime_dir / "runner_info.json").write_text(
        json.dumps(
            {
                "browser_product": "Chrome/146.0.0.0",
                "browser_user_agent": "Mozilla/5.0",
            }
        ),
        encoding="utf-8",
    )
    docker = SimpleNamespace(
        validator=SimpleNamespace(get_runtime_dir=lambda _p: runtime_dir)
    )
    core = SupervisorCore.__new__(SupervisorCore)
    core.docker = docker
    assert core._read_browser_version("p1") == (
        "Chrome/146.0.0.0",
        "Mozilla/5.0",
    )


# ---- Cross-process consistency: supervisor writes, runner reads ----------
# NOTE (t065): test_supervisor_written_credentials_are_accepted_by_runner
# was deleted wholesale here: it asserted the Runner accepts the
# supervisor-written credentials file and returns an inline-credential
# --proxy-server argument. t065 removes that path entirely — the
# Supervisor now writes credentials to the Profile secret dir (readable
# only by the forwarder) plus a credentialless endpoint file, and the
# Runner reads only the endpoint file. The new cross-process contract
# is covered by tests/unit/test_t065_proxy_forwarder_mounts.py
# (test_runner_resolves_credentialless_forwarder_arg,
# test_runner_fails_closed_on_endpoint_problems) and by the t065
# start_profile test there.


async def test_report_observed_running_carries_browser_version(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path
    (runtime_dir / "runner_info.json").write_text(
        json.dumps(
            {
                "browser_product": "Chrome/146.0.0.0",
                "browser_user_agent": "Mozilla/5.0",
            }
        ),
        encoding="utf-8",
    )
    posted: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        posted.append(json.loads(req.content))
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://api"
    ) as api:
        core = SupervisorCore.__new__(SupervisorCore)
        core.api = api
        core._token_file = None
        core.docker = SimpleNamespace(
            validator=SimpleNamespace(get_runtime_dir=lambda _p: runtime_dir)
        )
        assert await core._report_observed("p1", "inst_1", "running", 1)
    assert posted[0]["browser_product"] == "Chrome/146.0.0.0"
    assert posted[0]["browser_user_agent"] == "Mozilla/5.0"


async def test_report_observed_non_running_omits_version_fields() -> None:
    posted: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        posted.append(json.loads(req.content))
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://api"
    ) as api:
        core = SupervisorCore.__new__(SupervisorCore)
        core.api = api
        core._token_file = None
        assert await core._report_observed("p1", "inst_1", "stopped", 1)
    assert "browser_product" not in posted[0]
    assert "browser_user_agent" not in posted[0]


async def test_report_observed_422_is_final_and_never_degrades(
    tmp_path: Path,
) -> None:
    # t069 (supersedes the pre-t069 fallback expectation): a 422 from the
    # API is a contract rejection. The report is sent exactly once, with
    # the version fields, and reported as not delivered — the payload is
    # never resent with browser_product/browser_user_agent dropped.
    (tmp_path / "runner_info.json").write_text(
        json.dumps({"browser_product": "Chrome/146", "browser_user_agent": "UA"}),
        encoding="utf-8",
    )
    posted: list[dict] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        posted.append(body)
        return httpx.Response(422, json={"error": "validation_error"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://api"
    ) as api:
        core = SupervisorCore.__new__(SupervisorCore)
        core.api = api
        core._token_file = None
        core.docker = SimpleNamespace(
            validator=SimpleNamespace(get_runtime_dir=lambda _p: tmp_path)
        )
        assert not await core._report_observed("p1", "inst_1", "running", 1)
    assert len(posted) == 1
    assert posted[0]["browser_product"] == "Chrome/146"
    assert posted[0]["browser_user_agent"] == "UA"


# ---- Browser container mount + egress policy (AC-007 / AC-008) ----------
# NOTE (t065): test_browser_container_mounts_credentials_read_only_and_
# resolves_egress and test_start_profile_with_proxy_end_to_end were
# deleted wholesale here: both asserted the old contract — the Browser
# container mounts proxy_credentials.json read-only and the Runner
# returns an inline-credential --proxy-server argument. t065 removes
# that contract: the Browser never mounts the credentials file, its
# egress policy points at the credentialless forwarder endpoint, and
# the Runner reads only the endpoint file. Replacement coverage lives
# in tests/unit/test_t065_proxy_forwarder_mounts.py
# (test_browser_container_mounts_no_credentials,
# test_create_proxy_forwarder_wires_secret_only,
# test_start_profile_with_proxy_writes_secret_and_endpoint).


async def test_start_profile_surfaces_proxy_credentials_changed(tmp_path: Path) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from cbrowser.supervisor.path_validator import PathValidator
    from cbrowser.supervisor.port_allocator import PortAllocator

    root = (tmp_path / "data").resolve()
    (root / "engine_cache" / "geoip").mkdir(parents=True)
    validator = PathValidator(root)
    dirs = {"runtime": root / "runtime" / "p1"}
    dirs["runtime"].mkdir(parents=True)
    key_file = tmp_path / "agent_key"
    key_file.write_text("01234567890123456789012345678901", encoding="utf-8")
    key_file.chmod(0o600)

    adapter = SimpleNamespace(
        validator=validator,
        manage_ownership=False,
        prepare_profile_directories=lambda _: dirs,
        create_profile_network=AsyncMock(),
        start_browser_container=AsyncMock(),
        start_stream_container=AsyncMock(),
        teardown_profile=AsyncMock(),
        ensure_runtime_cache=AsyncMock(),
    )
    events = SimpleNamespace(
        drain_runtime_events=AsyncMock(return_value=0),
        forward_exit_event=AsyncMock(),
        emit_event=AsyncMock(),
    )

    def handler(req: httpx.Request) -> httpx.Response:
        if "/proxies/" in req.url.path and req.url.path.endswith("/credentials"):
            return httpx.Response(
                200,
                json={
                    "scheme": "socks5",
                    "host": "h",
                    "port": 1080,
                    "username": "u",
                    "password": "pw",
                    "credential_revision": 9,
                    "proxy_credential_revision": 2,
                },
            )
        return httpx.Response(
            200,
            json={"status": "ok", "desired_state": "running", "restart_blocked": False},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://api"
    ) as api:
        core = SupervisorCore(
            docker_adapter=adapter,
            port_allocator=PortAllocator(30000, 30010),
            event_forwarder=events,
            api_client=api,
            token_file=None,
            agent_key_file=key_file,
        )
        core.report_terminal_observation = AsyncMock(return_value=True)  # type: ignore[method-assign]
        with pytest.raises(SupervisorProxyChanged) as exc:
            await core.start_profile(
                "p1", ProfileConfig(name="p1", proxy_id="px1")
            )
        assert str(exc.value) == SUP_PROXY_CHANGED
        assert "pw" not in str(exc.value)
        reason_kwargs = core.report_terminal_observation.call_args.kwargs
        assert reason_kwargs["reason"] == SUP_PROXY_CHANGED
    # No browser container is launched on a credential change.
    adapter.start_browser_container.assert_not_awaited()
