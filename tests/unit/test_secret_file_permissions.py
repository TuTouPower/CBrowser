"""Internal credential files must not be group/other readable."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from cbrowser.api.internal_gateway import read_gateway_token
from cbrowser.api.internal_supervisor import read_supervisor_token
from cbrowser.secret_files import read_secret_file
from cbrowser.supervisor.control_server import create_control_app
from cbrowser.supervisor.core import SupervisorCore
from cbrowser.supervisor.event_forwarder import EventForwarder
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.port_allocator import PortAllocator


def _secret(path: Path, mode: int, value: str = "a" * 32) -> Path:
    path.write_text(value, encoding="utf-8")
    path.chmod(mode)
    return path


def test_read_secret_file_requires_private_mode(tmp_path: Path) -> None:
    assert read_secret_file(_secret(tmp_path / "ok", 0o600)) == "a" * 32
    with pytest.raises(RuntimeError, match="group or others"):
        read_secret_file(_secret(tmp_path / "bad", 0o644))
    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        read_secret_file(_secret(tmp_path / "short", 0o600, "short"))


def test_internal_tokens_reject_group_readable_files(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="group or others"):
        read_supervisor_token(_secret(tmp_path / "sup", 0o644))
    with pytest.raises(RuntimeError, match="group or others"):
        read_gateway_token(_secret(tmp_path / "gw", 0o644))
    assert read_supervisor_token(_secret(tmp_path / "sup_ok", 0o600)) is not None


def test_control_and_gateway_clients_reject_group_readable_tokens(
    tmp_path: Path,
) -> None:
    from cbrowser.supervisor.gateway_client import GatewayControlClient

    bad = _secret(tmp_path / "control", 0o644)
    with pytest.raises(ValueError, match="group or others"):
        create_control_app(SimpleNamespace(), bad)
    with pytest.raises(ValueError, match="group or others"):
        GatewayControlClient("http://127.0.0.1:1", bad)


@pytest.mark.asyncio
async def test_supervisor_token_read_rejects_group_readable_file(
    tmp_path: Path,
) -> None:
    import httpx

    async with httpx.AsyncClient(base_url="http://127.0.0.1:1", trust_env=False) as api:
        core = SupervisorCore(
            SimpleNamespace(validator=PathValidator(tmp_path)),
            PortAllocator(),
            EventForwarder(str(tmp_path / "unused"), tmp_path / "spool", client=api),
            api,
            token_file=_secret(tmp_path / "token", 0o644),
        )
        with pytest.raises(RuntimeError, match="group or others"):
            core._get_bearer_token()
