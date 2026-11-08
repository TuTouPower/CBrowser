from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.domain.models import PreviewPolicySyncRequest
from cbrowser.preview import (
    PreviewMeta,
    PreviewPolicy,
    commit_preview,
    preview_dir,
    read_meta,
    read_policy,
    write_policy,
)
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.core import ActiveSession, SupervisorCore
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator

NOTIFY_PATH = "/api/v1/internal/supervisor/profiles/profile/preview"


class _FakeAPI:
    def __init__(self) -> None:
        self.posts: list[tuple[str, dict | None]] = []

    async def post(self, url, *, headers=None, json=None):
        self.posts.append((url, json))
        return SimpleNamespace(status_code=200)


def _core(tmp_path: Path) -> tuple[SupervisorCore, _FakeAPI]:
    api = _FakeAPI()
    core = SupervisorCore(
        SimpleNamespace(validator=PathValidator(tmp_path)),
        PortAllocator(),
        None,
        api,
    )
    core._sessions["profile"] = ActiveSession(
        "profile", "inst_1", 1, 30000, "browser", "stream"
    )
    return core, api


def _pdir(core: SupervisorCore, profile_id: str = "profile") -> Path:
    return preview_dir(core.docker.validator.data_root, profile_id)


def _control_uds(calls: list):
    @asynccontextmanager
    async def factory(_profile_id):
        async def post(url, json=None, **kwargs):
            calls.append((url, json))
            return SimpleNamespace(status_code=200)

        async def get(url, **kwargs):
            return SimpleNamespace(status_code=503, json=lambda: {})

        yield SimpleNamespace(post=post, get=get)

    return factory


def _health_uds(payload: dict):
    @asynccontextmanager
    async def factory(_profile_id):
        async def get(url, **kwargs):
            return SimpleNamespace(status_code=200, json=lambda: payload)

        async def post(url, json=None, **kwargs):
            return SimpleNamespace(status_code=200)

        yield SimpleNamespace(get=get, post=post)

    return factory


def _health(captured_at, instance: str = "inst_1") -> dict:
    return {
        "status": "ok",
        "ready": True,
        "display_ready": True,
        "browser_ready": True,
        "audio_ready": True,
        "cdp_ready": True,
        "profile_id": "profile",
        "runtime_instance_id": instance,
        "config_version": 1,
        "details": {"preview_captured_at": captured_at},
    }


@pytest.mark.asyncio
async def test_apply_preview_policy_writes_policy_and_dispatches_control(
    tmp_path: Path,
) -> None:
    core, _ = _core(tmp_path)
    control_calls: list = []
    core._agent_uds_client = _control_uds(control_calls)  # type: ignore[method-assign]

    await core.apply_preview_policy(
        "profile",
        PreviewPolicySyncRequest(
            enabled=True, epoch=3, runtime_instance_id="inst_1", request_id="r1"
        ),
    )

    assert read_policy(_pdir(core)) == PreviewPolicy(
        enabled=True, epoch=3, runtime_instance_id="inst_1"
    )
    assert control_calls == [
        (
            "/control",
            {
                "action": "preview_policy",
                "enabled": True,
                "epoch": 3,
                "runtime_instance_id": "inst_1",
                "request_id": "r1",
            },
        )
    ]


@pytest.mark.asyncio
async def test_disabled_policy_clears_existing_preview(tmp_path: Path) -> None:
    core, _ = _core(tmp_path)
    core._agent_uds_client = _control_uds([])  # type: ignore[method-assign]
    directory = _pdir(core)
    policy = PreviewPolicy(enabled=True, epoch=2, runtime_instance_id="inst_1")
    write_policy(directory, policy)
    assert commit_preview(
        directory,
        b"\xff\xd8frame",
        PreviewMeta(
            captured_at="T0", runtime_instance_id="inst_1", policy_epoch=2
        ),
        policy,
    )
    assert (directory / "latest.jpg").is_file()
    assert read_meta(directory) is not None

    await core.apply_preview_policy(
        "profile",
        PreviewPolicySyncRequest(
            enabled=False, epoch=3, runtime_instance_id="inst_1", request_id="r2"
        ),
    )

    assert not (directory / "latest.jpg").exists()
    assert not (directory / "meta.json").exists()
    assert read_policy(directory) == PreviewPolicy(
        enabled=False, epoch=3, runtime_instance_id="inst_1"
    )


@pytest.mark.asyncio
async def test_stale_instance_and_duplicate_request_fence_control_dispatch(
    tmp_path: Path,
) -> None:
    core, _ = _core(tmp_path)
    control_calls: list = []
    core._agent_uds_client = _control_uds(control_calls)  # type: ignore[method-assign]

    await core.apply_preview_policy(
        "profile",
        PreviewPolicySyncRequest(
            enabled=True, epoch=3, runtime_instance_id="inst_STALE", request_id="r1"
        ),
    )
    assert control_calls == []

    await core.apply_preview_policy(
        "profile",
        PreviewPolicySyncRequest(
            enabled=True, epoch=4, runtime_instance_id="inst_1", request_id="r2"
        ),
    )
    assert len(control_calls) == 1

    await core.apply_preview_policy(
        "profile",
        PreviewPolicySyncRequest(
            enabled=True, epoch=4, runtime_instance_id="inst_1", request_id="r2"
        ),
    )
    assert len(control_calls) == 1


@pytest.mark.asyncio
async def test_preview_captured_at_change_notifies_api(tmp_path: Path) -> None:
    core, api = _core(tmp_path)
    directory = _pdir(core)
    policy = PreviewPolicy(enabled=True, epoch=5, runtime_instance_id="inst_1")
    write_policy(directory, policy)
    assert commit_preview(
        directory,
        b"\xff\xd8frame",
        PreviewMeta(
            captured_at="T1", runtime_instance_id="inst_1", policy_epoch=5
        ),
        policy,
    )

    core._agent_uds_client = _health_uds(_health("T1"))  # type: ignore[method-assign]
    health = await core._query_agent_health("profile")
    assert health is not None
    notifs = [p for p in api.posts if p[0].endswith("/preview")]
    assert len(notifs) == 1
    assert notifs[0][0] == NOTIFY_PATH
    assert notifs[0][1] == {
        "captured_at": "T1",
        "runtime_instance_id": "inst_1",
        "policy_epoch": 5,
    }

    await core._query_agent_health("profile")
    assert len([p for p in api.posts if p[0].endswith("/preview")]) == 1

    assert commit_preview(
        directory,
        b"\xff\xd8frame",
        PreviewMeta(
            captured_at="T2", runtime_instance_id="inst_1", policy_epoch=5
        ),
        policy,
    )
    core._agent_uds_client = _health_uds(_health("T2"))  # type: ignore[method-assign]
    await core._query_agent_health("profile")
    assert len([p for p in api.posts if p[0].endswith("/preview")]) == 2


@pytest.mark.asyncio
async def test_stale_epoch_notification_is_dropped(tmp_path: Path) -> None:
    core, api = _core(tmp_path)
    directory = _pdir(core)
    write_policy(
        directory,
        PreviewPolicy(enabled=True, epoch=6, runtime_instance_id="inst_1"),
    )
    (directory / "meta.json").write_text(
        PreviewMeta(
            captured_at="T1", runtime_instance_id="inst_1", policy_epoch=5
        ).model_dump_json(),
        encoding="utf-8",
    )
    (directory / "latest.jpg").write_bytes(b"\xff\xd8")

    core._agent_uds_client = _health_uds(_health("T1"))  # type: ignore[method-assign]
    await core._query_agent_health("profile")

    assert [p for p in api.posts if p[0].endswith("/preview")] == []


@pytest.mark.asyncio
async def test_mismatched_instance_notification_is_dropped(tmp_path: Path) -> None:
    core, api = _core(tmp_path)
    directory = _pdir(core)
    policy = PreviewPolicy(enabled=True, epoch=5, runtime_instance_id="inst_1")
    write_policy(directory, policy)
    (directory / "meta.json").write_text(
        PreviewMeta(
            captured_at="T1", runtime_instance_id="inst_OLD", policy_epoch=5
        ).model_dump_json(),
        encoding="utf-8",
    )
    (directory / "latest.jpg").write_bytes(b"\xff\xd8")

    core._agent_uds_client = _health_uds(_health("T1"))  # type: ignore[method-assign]
    await core._query_agent_health("profile")

    assert [p for p in api.posts if p[0].endswith("/preview")] == []


@pytest.mark.asyncio
async def test_preview_policy_endpoint_requires_token_and_applies(
    tmp_path: Path,
) -> None:
    token = "s" * 48
    token_file = tmp_path / "supervisor_token"
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)
    core, _ = _core(tmp_path)
    control_calls: list = []
    core._agent_uds_client = _control_uds(control_calls)  # type: ignore[method-assign]
    app = create_control_app(core, token_file)
    body = {
        "enabled": True,
        "epoch": 7,
        "runtime_instance_id": "inst_1",
        "request_id": "r9",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://supervisor"
    ) as client:
        denied = await client.post(
            "/supervisor/v1/profiles/profile/preview-policy", json=body
        )
        assert denied.status_code == 401
        ok = await client.post(
            "/supervisor/v1/profiles/profile/preview-policy",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
    assert ok.status_code == 200
    assert ok.json() == {"status": "ok"}
    assert read_policy(_pdir(core)).epoch == 7
    assert len(control_calls) == 1


@pytest.mark.asyncio
async def test_apply_preview_policy_fences_stale_epoch_instance_and_duplicate(
    tmp_path: Path,
) -> None:
    core, _ = _core(tmp_path)
    control_calls: list = []
    core._agent_uds_client = _control_uds(control_calls)  # type: ignore[method-assign]
    directory = _pdir(core)
    write_policy(
        directory,
        PreviewPolicy(enabled=True, epoch=5, runtime_instance_id="inst_1"),
    )

    await core.apply_preview_policy(
        "profile",
        PreviewPolicySyncRequest(
            enabled=True, epoch=4, runtime_instance_id="inst_1", request_id="r-old"
        ),
    )
    assert read_policy(directory).epoch == 5
    assert control_calls == []

    await core.apply_preview_policy(
        "profile",
        PreviewPolicySyncRequest(
            enabled=False, epoch=6, runtime_instance_id="inst_2", request_id="r-stale"
        ),
    )
    assert read_policy(directory).epoch == 5
    assert control_calls == []

    await core.apply_preview_policy(
        "profile",
        PreviewPolicySyncRequest(
            enabled=True, epoch=6, runtime_instance_id="inst_1", request_id="r-fresh"
        ),
    )
    assert read_policy(directory).epoch == 6
    assert len(control_calls) == 1

    await core.apply_preview_policy(
        "profile",
        PreviewPolicySyncRequest(
            enabled=True, epoch=6, runtime_instance_id="inst_1", request_id="r-fresh"
        ),
    )
    assert len(control_calls) == 1
