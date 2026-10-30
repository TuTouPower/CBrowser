"""An old stop operation cannot act on a replacement runtime."""

from types import SimpleNamespace

import httpx
import pytest
from cbrowser.supervisor.core import ActiveSession, SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator


@pytest.mark.asyncio
@pytest.mark.parametrize("completed", [True, False])
async def test_old_stop_replay_keeps_replacement_session(tmp_path, completed):
    async with httpx.AsyncClient(base_url="http://127.0.0.1:1", trust_env=False) as api:
        events = EventForwarder(str(api.base_url), tmp_path / "spool", client=api)
        core = SupervisorCore(
            SimpleNamespace(validator=PathValidator(tmp_path)),
            PortAllocator(),
            events,
            api,
        )
        current = ActiveSession("profile", "new_runtime", 1, 30000, "browser", "stream")
        core._sessions["profile"] = current
        request = {"profile_id": "profile", "runtime_instance_id": "old_runtime"}
        result = dict(request, status="stopped")
        core.operations.begin("old_stop", request)
        if completed:
            core.operations.complete("old_stop", request, result)
        replay = await core.stop_profile(
            "profile", expected_instance="old_runtime", operation_id="old_stop"
        )
        assert replay == result
        assert core._sessions["profile"] is current
        with pytest.raises(ValueError, match="different request"):
            await core.stop_profile(
                "profile", expected_instance="new_runtime", operation_id="old_stop"
            )
