"""Lifecycle conflicts surface as HTTP 409 over the real control HTTP (A11)."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.core import LifecycleConflictError
from cbrowser.supervisor.port_allocator import PortPoolExhaustedError

TOKEN = "t" * 40


class _ConfigApi:
    async def get(self, _url: str, headers=None) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "profile_id": "profile_a",
                "version": 1,
                "config": {"name": "Profile A"},
            },
        )


def _core_with(error: Exception | None) -> SimpleNamespace:
    async def start_profile(**_kwargs):
        if error is not None:
            raise error
        return SimpleNamespace(runtime_instance_id="inst_1", udp_mux_port=40000)

    return SimpleNamespace(
        api=_ConfigApi(),
        _auth_headers=lambda: {},
        start_profile=start_profile,
        docker=SimpleNamespace(
            get_browser_container_name=lambda _pid: "browser-a",
            get_stream_container_name=lambda _pid: "stream-a",
        ),
    )


async def _post_start(tmp_path, core) -> httpx.Response:
    key = tmp_path / "control_token"
    key.write_text(TOKEN)
    key.chmod(0o600)
    app = create_control_app(core, key)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://supervisor"
    ) as client:
        return await client.post(
            "/supervisor/v1/profiles/start",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"profile_id": "profile_a", "config_version": 1},
        )


@pytest.mark.asyncio
async def test_lifecycle_conflict_maps_to_409_without_internal_detail(
    tmp_path,
) -> None:
    response = await _post_start(
        tmp_path,
        _core_with(LifecycleConflictError("Existing runtime secret-internal-xyz")),
    )
    assert response.status_code == 409
    assert "secret-internal-xyz" not in response.text


@pytest.mark.asyncio
async def test_port_exhaustion_maps_to_503(tmp_path) -> None:
    response = await _post_start(
        tmp_path, _core_with(PortPoolExhaustedError("pool empty"))
    )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_unexpected_failure_maps_to_500(tmp_path) -> None:
    response = await _post_start(
        tmp_path, _core_with(RuntimeError("boom-internal"))
    )
    assert response.status_code == 500
    assert "boom-internal" not in response.text
