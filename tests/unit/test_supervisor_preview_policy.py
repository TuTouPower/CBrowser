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
    frame_path,
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
                "params": {
                    "enabled": True,
                    "epoch": 3,
                    "runtime_instance_id": "inst_1",
                    "request_id": "r1",
                },
            },
        )
    ]




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


@pytest.mark.asyncio
async def test_preview_policy_control_payload_matches_agent_protocol(
    tmp_path: Path,
) -> None:
    from cbrowser.runtime_agent.protocol import ControlRequest

    core, _ = _core(tmp_path)
    control_calls: list = []
    core._agent_uds_client = _control_uds(control_calls)  # type: ignore[method-assign]

    await core.apply_preview_policy(
        "profile",
        PreviewPolicySyncRequest(
            enabled=True, epoch=3, runtime_instance_id="inst_1", request_id="r1"
        ),
    )

    assert len(control_calls) == 1
    # Agent-side ControlRequest is forbid + params-nested: the payload must
    # validate strictly, i.e. no flat extra keys beside action/params.
    parsed = ControlRequest.model_validate(control_calls[0][1])
    assert parsed.action == "preview_policy"
    assert parsed.params == {
        "enabled": True,
        "epoch": 3,
        "runtime_instance_id": "inst_1",
        "request_id": "r1",
    }


@pytest.mark.asyncio
async def test_apply_preview_policy_chowns_policy_to_runtime_uid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    core, _ = _core(tmp_path)
    core.docker.manage_ownership = True  # type: ignore[attr-defined]
    core.docker.runtime_uid = 1000  # type: ignore[attr-defined]
    core.docker.runtime_gid = 1000  # type: ignore[attr-defined]
    chowned: list = []

    def _record(fd, uid, gid, **kwargs):
        # fchown on the staging descriptor (shared atomic write, t062):
        # record whether the final path was already visible at that
        # moment — it must not be.
        chowned.append((fd, uid, gid, (_pdir(core) / "policy.json").exists()))

    monkeypatch.setattr("os.fchown", _record)
    core._agent_uds_client = _control_uds([])  # type: ignore[method-assign]

    await core.apply_preview_policy(
        "profile",
        PreviewPolicySyncRequest(
            enabled=True, epoch=3, runtime_instance_id="inst_1", request_id="r1"
        ),
    )

    # Ownership is set on the staging file before replace: no root:root
    # 0600 window on the final path.
    assert len(chowned) == 1
    assert chowned[0][1:3] == (1000, 1000)
    assert chowned[0][3] is False
    assert read_policy(_pdir(core)) == PreviewPolicy(
        enabled=True, epoch=3, runtime_instance_id="inst_1"
    )
    assert list(_pdir(core).glob(".*.tmp")) == []


@pytest.mark.asyncio
async def test_apply_preview_policy_chown_failure_leaves_no_root_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cbrowser.supervisor.docker_adapter import DockerSandboxError

    core, _ = _core(tmp_path)
    core.docker.manage_ownership = True  # type: ignore[attr-defined]
    core.docker.runtime_uid = 1000  # type: ignore[attr-defined]
    core.docker.runtime_gid = 1000  # type: ignore[attr-defined]

    def _fail_chown(*_args, **_kwargs):
        raise OSError("chown failed")

    monkeypatch.setattr("os.fchown", _fail_chown)
    core._agent_uds_client = _control_uds([])  # type: ignore[method-assign]

    with pytest.raises(DockerSandboxError):
        await core.apply_preview_policy(
            "profile",
            PreviewPolicySyncRequest(
                enabled=True, epoch=3, runtime_instance_id="inst_1", request_id="r1"
            ),
        )

    assert not (_pdir(core) / "policy.json").exists()
    assert list(_pdir(core).glob("*.tmp")) == []


def _failing_uds(calls: list, *, status: int = 500):
    @asynccontextmanager
    async def factory(_profile_id):
        async def post(url, json=None, **kwargs):
            calls.append((url, json))
            return SimpleNamespace(status_code=status)

        async def get(url, **kwargs):
            return SimpleNamespace(status_code=503, json=lambda: {})

        yield SimpleNamespace(post=post, get=get)

    return factory


def _none_uds():
    @asynccontextmanager
    async def factory(_profile_id):
        yield None

    return factory


def _raising_uds():
    @asynccontextmanager
    async def factory(_profile_id):
        async def post(url, json=None, **kwargs):
            raise ConnectionError("uds down")

        async def get(url, **kwargs):
            raise ConnectionError("uds down")

        yield SimpleNamespace(post=post, get=get)

    return factory


@pytest.mark.asyncio
async def test_apply_preview_policy_dispatch_failure_raises_and_keeps_retryable(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from cbrowser.supervisor.core import RuntimeUnavailableError

    factories = [
        _none_uds(),
        _failing_uds([], status=500),
        _failing_uds([], status=403),
        _raising_uds(),
    ]
    for index, factory in enumerate(factories):
        core, _ = _core(tmp_path)
        core._sessions["profile"] = core._sessions["profile"]
        core._agent_uds_client = factory  # type: ignore[method-assign]
        req = PreviewPolicySyncRequest(
            enabled=True,
            epoch=10 + index,
            runtime_instance_id="inst_1",
            request_id=f"r-retry-{index}",
        )
        with caplog.at_level("ERROR", logger="cbrowser.supervisor.core"):
            with pytest.raises(RuntimeUnavailableError):
                await core.apply_preview_policy("profile", req)
        assert any(
            r.levelname == "ERROR" and "profile" in r.getMessage()
            for r in caplog.records
        )
        caplog.clear()
        # failure must not poison dedup: same request_id retries dispatch
        ok_calls: list = []
        core._agent_uds_client = _control_uds(ok_calls)  # type: ignore[method-assign]
        await core.apply_preview_policy("profile", req)
        assert len(ok_calls) == 1


@pytest.mark.asyncio
async def test_apply_preview_policy_duplicate_after_success_still_skipped(
    tmp_path: Path,
) -> None:
    core, _ = _core(tmp_path)
    control_calls: list = []
    core._agent_uds_client = _control_uds(control_calls)  # type: ignore[method-assign]

    req = PreviewPolicySyncRequest(
        enabled=True, epoch=3, runtime_instance_id="inst_1", request_id="r-dup"
    )
    await core.apply_preview_policy("profile", req)
    assert len(control_calls) == 1
    await core.apply_preview_policy("profile", req)
    assert len(control_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["http", "transport"])
async def test_observation_failure_retries_same_frame(tmp_path, caplog, failure):
    from cbrowser.runtime_agent.protocol import HealthResponse

    core, api = _core(tmp_path)
    directory = _pdir(core)
    policy = PreviewPolicy(enabled=True, epoch=5, runtime_instance_id="inst_1")
    write_policy(directory, policy)
    commit_preview(directory, b"frame", PreviewMeta(captured_at="T1", runtime_instance_id="inst_1", policy_epoch=5), policy)
    original = api.post
    attempts = 0

    async def flaky(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            if failure == "transport":
                raise ConnectionError("private detail must not be logged")
            return SimpleNamespace(status_code=503)
        return await original(*args, **kwargs)

    api.post = flaky
    health = HealthResponse.model_validate(_health("T1"))
    with caplog.at_level("WARNING"):
        await core._observe_preview_capture("profile", health)
        await core._observe_preview_capture("profile", health)
        await core._observe_preview_capture("profile", health)
    assert attempts == 2
    assert core._preview_captured_at["profile"] == "T1"
    assert any(r.levelname == "WARNING" and "Preview observation" in r.message for r in caplog.records)
    assert "private detail" not in caplog.text


@pytest.mark.asyncio
async def test_invalid_observation_does_not_poison_dedup(tmp_path):
    from cbrowser.runtime_agent.protocol import HealthResponse

    core, api = _core(tmp_path)
    directory = _pdir(core)
    policy = PreviewPolicy(enabled=True, epoch=5, runtime_instance_id="inst_1")
    write_policy(directory, policy)
    health = HealthResponse.model_validate(_health("T1"))
    await core._observe_preview_capture("profile", health)
    assert api.posts == []
    commit_preview(directory, b"frame", PreviewMeta(captured_at="T1", runtime_instance_id="inst_1", policy_epoch=5), policy)
    await core._observe_preview_capture("profile", health)
    assert len(api.posts) == 1


def test_preview_state_is_forgotten_with_runtime_generation(tmp_path):
    core, _ = _core(tmp_path)
    core._preview_request_ids["profile"] = "r"
    core._preview_captured_at["profile"] = "T1"
    core._preview_warning_at["profile"] = 1.0
    core.forget_instance_events("profile", "inst_1")
    assert "profile" not in core._preview_request_ids
    assert "profile" not in core._preview_captured_at
    assert "profile" not in core._preview_warning_at


def test_observation_warning_is_rate_limited(tmp_path, caplog):
    core, _ = _core(tmp_path)
    with caplog.at_level("WARNING"):
        for _ in range(3):
            core._warn_preview_observation("profile", "ConnectionError")
    assert len(caplog.records) == 1



@pytest.mark.asyncio
async def test_supervisor_revocation_removes_all_immutable_frames_and_metadata(tmp_path):
    core, _ = _core(tmp_path)
    core._agent_uds_client = _control_uds([])
    directory = _pdir(core)
    policy = PreviewPolicy(enabled=True,epoch=2,runtime_instance_id="inst_1")
    write_policy(directory,policy)
    frames=[]
    for index in range(2):
        meta=PreviewMeta(captured_at=f"T{index}",runtime_instance_id="inst_1",policy_epoch=2)
        assert commit_preview(directory,f"frame-{index}".encode(),meta,policy)
        frames.append(frame_path(directory,read_meta(directory)))
    assert len(set(frames))==2 and all(p.is_file() for p in frames)
    await core.apply_preview_policy("profile",PreviewPolicySyncRequest(enabled=False,epoch=3,runtime_instance_id="inst_1",request_id="revoke"))
    assert all(not p.exists() for p in frames)
    assert list(directory.glob("*.jpg"))==[]
    assert read_meta(directory) is None
    assert read_policy(directory)==PreviewPolicy(enabled=False,epoch=3,runtime_instance_id="inst_1")
