"""t069 strict control-plane contracts (AC-001/002/003/004).

Negative matrix for the unified ErrorResponse, the single-shot
observed-state report, deployment ownership, persisted launch_args and
the network CLI. The [deploy] half of AC-003 (real Docker topology) is
not covered here by design; these tests pin the pre-Docker behaviour:
fake clients record zero mutations when identity is missing.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.api.runtime_coordinator import (
    DOWNSTREAM_PROTOCOL_ERROR,
    _downstream_error_text,
)
from cbrowser.network_config_cli import main as network_cli_main
from cbrowser.shared.error_response import parse_error_response
from cbrowser.supervisor.docker_adapter import DockerAdapter
from cbrowser.supervisor.gateway_client import GatewayControlClient
from cbrowser.supervisor.network_spec import network_ownership_matches
from cbrowser.supervisor.path_validator import PathValidator
from cbrowser.supervisor.runner import run_supervisor

REPO_ROOT = Path(__file__).resolve().parents[2]

VALID_BODY = {
    "error": "agent_unavailable",
    "message": "Agent for profile p1 is unavailable",
    "retryable": True,
}


# ---------------------------------------------------------------- parser


def test_parser_accepts_the_unified_shape():
    parsed = parse_error_response(VALID_BODY)
    assert parsed is not None
    assert parsed.error == "agent_unavailable"
    assert parsed.message == "Agent for profile p1 is unavailable"
    assert parsed.retryable is True


@pytest.mark.parametrize(
    "body",
    [
        {"detail": "Agent unavailable"},  # legacy detail shape
        {"detail": {"code": "control_taken", "message": "taken"}},
        {"error": "x", "message": "y"},  # retryable missing
        {"error": "x", "retryable": True},  # message missing
        {"message": "y", "retryable": True},  # error missing
        {"error": "", "message": "y", "retryable": True},  # empty error
        {"error": "x", "message": "", "retryable": True},  # empty message
        {"error": "x", "message": "y", "retryable": "yes"},  # mistyped
        {"error": 7, "message": "y", "retryable": True},
        "raw text body",
        ["not", "a", "dict"],
        None,
    ],
)
def test_parser_rejects_non_conforming_bodies(body):
    assert parse_error_response(body) is None


# ------------------------------------------------------- coordinator text


class _Resp:
    def __init__(self, body=None, *, json_error: bool = False, status: int = 503):
        self._body = body
        self._json_error = json_error
        self.status_code = status
        self.text = "raw downstream text"

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._body


def test_downstream_text_preserves_unified_error_and_message():
    assert _downstream_error_text(_Resp(VALID_BODY)) == (
        "agent_unavailable: Agent for profile p1 is unavailable"
    )


@pytest.mark.parametrize(
    "resp",
    [
        _Resp({"detail": "legacy reason"}),
        _Resp({"error": "only_error"}),
        _Resp(json_error=True),
        _Resp("plain text"),
        _Resp({}),
    ],
)
def test_downstream_text_non_conforming_is_a_protocol_error(resp):
    text = _downstream_error_text(resp)
    assert text == DOWNSTREAM_PROTOCOL_ERROR
    assert "legacy reason" not in text
    assert "raw downstream text" not in text


# --------------------------------------------------------- gateway client


def _gateway_client(tmp_path: Path, response: httpx.Response) -> GatewayControlClient:
    token_file = tmp_path / "gateway_token"
    token_file.write_text("g" * 40, encoding="utf-8")
    token_file.chmod(0o600)
    client = GatewayControlClient("http://gateway.invalid", token_file)

    def handler(request: httpx.Request) -> httpx.Response:
        return response

    client._client = httpx.AsyncClient(
        base_url="http://gateway.invalid",
        transport=httpx.MockTransport(handler),
    )
    return client


@pytest.mark.asyncio
async def test_agent_registered_unavailable_message_means_absent(tmp_path):
    client = _gateway_client(tmp_path, httpx.Response(503, json=VALID_BODY))
    assert await client.agent_registered("p1", "inst1") is False


@pytest.mark.asyncio
async def test_agent_registered_not_reported_yet_means_registered(tmp_path):
    body = {
        "error": "agent_unavailable",
        "message": "Agent for profile p1 has not reported yet",
        "retryable": True,
    }
    client = _gateway_client(tmp_path, httpx.Response(503, json=body))
    assert await client.agent_registered("p1", "inst1") is True


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, json={"detail": "Agent unavailable for this instance"}),
        httpx.Response(503, json={"message": "Agent unavailable"}),
        httpx.Response(503, content=b"not json"),
    ],
)
@pytest.mark.asyncio
async def test_agent_registered_non_conforming_503_is_unknown(tmp_path, response):
    client = _gateway_client(tmp_path, response)
    assert await client.agent_registered("p1", "inst1") is None


# ------------------------------------------------------------- 422 single


@pytest.mark.asyncio
async def test_report_observed_422_is_single_shot_and_not_delivered(
    tmp_path, monkeypatch
):
    from cbrowser.supervisor.core import SupervisorCore
    from cbrowser.supervisor.event_forwarder import EventForwarder
    from cbrowser.supervisor.port_allocator import PortAllocator

    posts: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posts.append(json.loads(request.content))
        return httpx.Response(
            422,
            json={
                "error": "validation_error",
                "message": "extra fields",
                "retryable": False,
            },
        )

    api = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://api",
        trust_env=False,
    )
    core = SupervisorCore(
        # docker adapter is untouched by this path; only its validator's
        # data_root is read while the core loads event cursors.
        SimpleNamespace(validator=PathValidator(tmp_path)),
        PortAllocator(),
        EventForwarder("http://api", tmp_path / "spool", client=api),
        api,
    )
    monkeypatch.setattr(
        core, "_read_browser_version", lambda pid: ("Chrome/130.0", "UA/130")
    )

    delivered = await core._report_observed("p1", "inst1", "running", 1)

    assert delivered is False
    # Exactly one request, carrying the version fields: no degraded
    # resend without browser_product/browser_user_agent ever happens.
    assert len(posts) == 1
    assert posts[0]["browser_product"] == "Chrome/130.0"
    assert posts[0]["browser_user_agent"] == "UA/130"


# -------------------------------------------------------------- ownership


OWNED_LABELS = {"com.cbrowser.instance-id": "dep-1"}


@pytest.mark.parametrize(
    "labels,deployment_id,expected",
    [
        (OWNED_LABELS, "dep-1", True),
        (OWNED_LABELS, "dep-2", False),
        (OWNED_LABELS, None, False),
        (OWNED_LABELS, "", False),
        ({}, "dep-1", False),
        ({"com.cbrowser.profile-id": "p1", "com.cbrowser.prefix": "cb"}, None, False),
    ],
)
def test_network_ownership_only_instance_id(labels, deployment_id, expected):
    assert network_ownership_matches(labels, deployment_id=deployment_id) is expected


_BROWSER = "sha256:f2a8d42810c13c8480b83e4308669c754e86b0fe4a24c6215159e43a8d1f5346"
_STREAM = "sha256:072e86762d2f1810e86a2d20169d4be451b5a19e0ebabc880e882de63ac0d531"


def _adapter(tmp_path: Path, deployment_instance_id) -> DockerAdapter:
    root = tmp_path / "data"
    engine = root / "engine_cache"
    engine.mkdir(parents=True)
    (engine / "geoip").mkdir(parents=True)
    client = SimpleNamespace(
        containers=SimpleNamespace(list=lambda **kwargs: []),
    )
    return DockerAdapter(
        path_validator=PathValidator(root),
        engine_cache_dir=engine,
        docker_client=client,
        browser_image=_BROWSER,
        stream_image=_STREAM,
        policy_image=_BROWSER,
        deployment_instance_id=deployment_instance_id,
    )


def test_adapter_owns_nothing_when_unconfigured(tmp_path):
    adapter = _adapter(tmp_path, None)
    assert adapter._owns_deployment(OWNED_LABELS) is False
    assert adapter._owns_deployment({}) is False


def test_adapter_owns_only_matching_instance_id(tmp_path):
    adapter = _adapter(tmp_path, "dep-1")
    assert adapter._owns_deployment(OWNED_LABELS) is True
    assert adapter._owns_deployment({"com.cbrowser.instance-id": "dep-2"}) is False
    assert adapter._owns_deployment({}) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [None, "", "   "])
async def test_supervisor_startup_requires_deployment_instance_id(tmp_path, missing):
    with pytest.raises(ValueError, match="deployment instance id"):
        await run_supervisor(
            api_url="http://api.invalid",
            data_root=tmp_path / "data",
            engine_cache=tmp_path / "engine",
            deployment_instance_id=missing,
        )


def test_deploy_sh_has_no_label_missing_project_exemption():
    text = (REPO_ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    assert '[ -z "$deployment_id" ]' not in text
    assert "containers created before the label existed" not in text


# ------------------------------------------------------------ launch args


def _profile_model(**overrides):
    fields = dict(
        id="p-bad",
        name="bad",
        fingerprint_seed=123456,
        group_id=None,
        proxy_id=None,
        timezone=None,
        locale=None,
        screen_width=1920,
        screen_height=1080,
        gpu_family="nvidia",
        humanize=True,
        human_preset="default",
        geoip=False,
        clipboard_sync=False,
        auto_launch=False,
        color_scheme="light",
        fingerprint_platform="windows",
        font_set_id=None,
        launch_args=json.dumps(["--load-extension=/tmp/evil"]),
        extension_paths="[]",
        allow_3p_cookies=True,
        set_google_default=True,
        capture_preview=True,
        restore_session=True,
        transparent_proxy=False,
        portable_cookies=True,
        notes=None,
        sort_order=0,
        display_number=7,
        user_data_dir="/tmp/p-bad",
        current_config_version=1,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_repository_rejects_invalid_stored_launch_args_naming_profile():
    with pytest.raises(RuntimeError, match="p-bad"):
        ProfileRepository._to_domain_profile(_profile_model())


def test_repository_loads_valid_stored_launch_args_verbatim():
    model = _profile_model(launch_args=json.dumps(["--mute-audio", "--lang=en-US"]))
    profile = ProfileRepository._to_domain_profile(model)
    assert profile.config.launch_args == ["--mute-audio", "--lang=en-US"]


# ------------------------------------------------------------ network cli


def test_network_cli_render_drops_dead_outputs(tmp_path, capsys):
    rc = network_cli_main(
        ["render", "--network-dir", str(tmp_path / "net"), "--https-port", "56661"]
    )
    out = capsys.readouterr().out
    assert rc == 0
    keys = {line.split("=", 1)[0] for line in out.strip().splitlines()}
    assert keys == {"HTTPS_PORT", "CADDYFILE_SHA256"}
    assert "BIND_HOST" not in out
    assert "PUBLIC_ORIGIN" not in out
