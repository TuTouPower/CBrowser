"""Behavior-equivalence checks for modules split out of large coordinators."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from cbrowser.api.v1.runtime_views import make_runtime_response, resolve_operation_id
from cbrowser.domain.models import ProfileRuntime
from cbrowser.stream_agent.messaging import (
    inject_controller_token,
    normalize_close_code,
    parse_hello_metadata,
    tunnel_close_envelope,
    tunnel_message_envelope,
)
from cbrowser.stream_agent.policy_rules import (
    sanitize_caller,
    sanitize_settings_message,
    should_block_client_verb,
)
from cbrowser.supervisor.container_spec import (
    browser_command,
    browser_labels,
    cache_init_environment,
    gated_entrypoint,
    stream_environment,
    stream_labels,
    stream_ports,
)
from cbrowser.supervisor.network_spec import (
    browser_network_name,
    endpoint_port,
    network_labels,
    network_ownership_matches,
    profile_network_name,
)
from cbrowser.supervisor.recovery_rules import (
    browser_terminated,
    exit_event_superseded,
    failure_budget_exhausted,
    index_containers_by_profile,
    is_brand_new_runtime,
    live_instance_ids,
    remaining_retry_seconds,
    retry_delay_for_failure,
    runtime_pair_active,
    stream_missing,
    terminal_observation,
)
from cbrowser.supervisor.volume_spec import browser_volumes, stream_volumes


def test_recovery_container_indexing_and_liveness() -> None:
    containers = [
        {"profile_id": "p1", "role": "browser", "instance_id": "i1"},
        {"profile_id": "p1", "role": "stream"},
        {"profile_id": None, "role": "browser", "instance_id": "ignored"},
        {"profile_id": "p2", "role": None, "instance_id": "ignored"},
    ]

    indexed = index_containers_by_profile(containers)

    assert set(indexed) == {"p1"}
    assert indexed["p1"]["browser"]["instance_id"] == "i1"
    assert live_instance_ids(indexed) == {"i1"}


def test_recovery_exit_classification_rules() -> None:
    assert stream_missing("running", None)
    assert stream_missing("running", {"status": "exited"})
    assert not stream_missing("running", {"status": "running"})
    assert not stream_missing("exited", None)

    reported = {"i1"}
    assert not browser_terminated("running", "i2", reported)
    assert not browser_terminated("exited", "i1", reported)
    assert browser_terminated("exited", "i2", reported)
    assert browser_terminated("dead", "i2", reported)


def test_recovery_fencing_and_observation_rules() -> None:
    instance = "i1"
    assert exit_event_superseded({"desired_state": "stopped"}, instance)
    assert exit_event_superseded({"runtime_instance_id": None}, instance)
    assert exit_event_superseded({"runtime_instance_id": "other"}, instance)
    assert not exit_event_superseded({"runtime_instance_id": instance}, instance)

    assert terminal_observation(0) == ("stopped", "normal_exit")
    assert terminal_observation(137) == ("error", "container_exit")


def test_recovery_schedule_predicates() -> None:
    assert retry_delay_for_failure(0) == 0.0
    assert retry_delay_for_failure(1) == 2.0
    assert retry_delay_for_failure(2) == 10.0
    assert retry_delay_for_failure(3) == 30.0

    assert remaining_retry_seconds(None, 2.0) == 0.0
    assert remaining_retry_seconds("invalid", 2.0) == 2.0
    remaining = remaining_retry_seconds(
        (datetime.now(UTC) - timedelta(seconds=5)).isoformat(), 10.0
    )
    assert 4.9 < remaining <= 5.0
    future = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
    assert 14.9 < remaining_retry_seconds(future, 10.0) <= 15.0

    assert is_brand_new_runtime(0, None)
    assert not is_brand_new_runtime(0, "exit_1")
    assert not is_brand_new_runtime(1, None)

    browser = {"status": "running", "instance_id": "i1"}
    stream = {"status": "running"}
    assert runtime_pair_active("stopped", "i1", browser, stream)
    assert not runtime_pair_active("error", "i1", browser, stream)
    assert not runtime_pair_active("stopped", "i2", browser, stream)
    assert not runtime_pair_active("stopped", "i1", None, stream)

    assert not failure_budget_exhausted(3, 4)
    assert failure_budget_exhausted(4, 4)


def test_container_spec_entrypoint_and_browser_arguments() -> None:
    assert gated_entrypoint("i1", "browser") == [
        "/usr/bin/tini",
        "-g",
        "--",
        "python3",
        "/run/cbrowser_policy/startup_gate.py",
        "--instance-id",
        "i1",
        "--role",
        "browser",
        "--",
        "/app/entrypoint.sh",
    ]
    command = browser_command("p1", "i1", ":99")
    assert "/data/profiles/p1/profile" in command
    assert "/data/runtime-events/p1" in command
    assert command[-1] == ":99"


def test_container_spec_browser_volumes_and_labels(tmp_path: Path) -> None:
    dirs = {
        name: tmp_path / name
        for name in ("profile", "events", "exchange", "runtime", "x11", "pulse")
    }
    gate = tmp_path / "gate"
    engine = tmp_path / "engine"
    geoip = tmp_path / "geoip"

    volumes = browser_volumes(
        profile_id="p1",
        dirs=dirs,
        gate=gate,
        engine_cache=engine,
        geoip_cache=geoip,
    )

    assert volumes[str(gate)] == {"bind": "/run/cbrowser_policy", "mode": "ro"}
    assert volumes[str(dirs["profile"])] == {
        "bind": "/data/profiles/p1/profile",
        "mode": "rw",
    }
    assert volumes[str(engine)] == {"bind": "/data/engine-cache", "mode": "ro"}
    assert volumes[str(geoip)] == {
        "bind": "/data/engine-cache/geoip",
        "mode": "ro",
    }
    assert browser_labels("cb", "p1", "i1", 3) == {
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.profile-id": "p1",
        "com.cbrowser.instance-id": "i1",
        "com.cbrowser.role": "browser",
        "com.cbrowser.network-policy": "v1",
        "com.cbrowser.config-version": "3",
        "com.cbrowser.prefix": "cb",
    }


def test_container_spec_stream_specs(tmp_path: Path) -> None:
    volumes = stream_volumes(
        gate=tmp_path / "gate",
        x11_socket=tmp_path / "X99",
        xauth_file=tmp_path / "Xauthority",
        pulse_dir=tmp_path / "pulse",
        secret_file=tmp_path / "secret",
        selkies_file=tmp_path / "selkies",
    )
    assert volumes[str(tmp_path / "gate")] == {
        "bind": "/run/cbrowser_policy",
        "mode": "ro",
    }
    assert volumes[str(tmp_path / "secret")] == {
        "bind": "/tmp/secret.txt",
        "mode": "ro",
    }

    env = stream_environment(
        public_ip="203.0.113.1",
        display=":99",
        profile_id="p1",
        runtime_instance_id="i1",
        gateway_url="ws://gateway:8080/stream",
        config_version="3",
        udp_mux_port=30006,
        media_addresses={"coturn_ip": "10.0.0.5"},
        screen_width=1280,
        screen_height=720,
    )
    assert env["CBROWSER_CONFIG_VERSION"] == "3"
    assert env["CBROWSER_SCREEN_WIDTH"] == "1280"
    assert env["CBROWSER_SCREEN_HEIGHT"] == "720"
    assert env["SELKIES_STUN_HOST"] == "10.0.0.5"
    assert env["SELKIES_TURN_PORT"] == "3478"
    assert stream_ports(30006) == {"30006/udp": ("127.0.0.1", 30006)}
    assert stream_labels("cb", "p1", "i1", "3")["com.cbrowser.role"] == "stream"


def test_container_spec_cache_specs() -> None:
    assert cache_init_environment(True, "marker.json", "run1") == {
        "PYTHONDONTWRITEBYTECODE": "1",
        "CLOAKBROWSER_CACHE_DIR": "/data/engine-cache",
        "CBROWSER_INIT_GEOIP": "1",
        "CBROWSER_INIT_MARKER": "marker.json",
        "CBROWSER_INIT_RUN_ID": "run1",
    }
    assert cache_init_environment(False, "marker.json", "run1")[
        "CBROWSER_INIT_GEOIP"
    ] == "0"


def test_network_spec_names_labels_and_ownership() -> None:
    assert profile_network_name("cb", "p1") == "cb-net-p1"
    assert browser_network_name("cb", "p1") == "cb-browser-net-p1"
    assert network_labels("cb", "p1") == {
        "com.cbrowser.managed-by": "supervisor",
        "com.cbrowser.profile-id": "p1",
        "com.cbrowser.prefix": "cb",
    }
    labels = network_labels("cb", "p1")
    assert network_ownership_matches("cb", "cb-net-p1", labels)
    assert network_ownership_matches("cb", "cb-browser-net-p1", labels)
    assert not network_ownership_matches("cb", "cb-net-p2", labels)
    assert not network_ownership_matches("other", "cb-net-p1", labels)
    assert not network_ownership_matches(
        "cb", "cb-net-p1", {"com.cbrowser.profile-id": 1}
    )
    assert endpoint_port("http") == 80
    assert endpoint_port("wss") == 443
    assert endpoint_port("socks5h") == 1080
    assert endpoint_port("unknown") is None


def test_messaging_close_code_normalization() -> None:
    assert normalize_close_code(4001) == 4001
    assert normalize_close_code(1000) == 1000
    assert normalize_close_code(None) == 1000
    assert normalize_close_code("4001") == 1000
    assert normalize_close_code(999) == 1000
    assert normalize_close_code(5000) == 1000


def test_messaging_hello_token_injection() -> None:
    metadata = {
        "client_tab_id": "tab1",
        "resume_key": "resume1",
        "keep": True,
    }
    data = f"HELLO client {json.dumps(metadata)}"

    parsed = parse_hello_metadata(data)
    assert parsed is not None
    parts, meta = parsed
    assert meta["client_tab_id"] == "tab1"

    injected = inject_controller_token(parts, meta, "secret")
    assert json.loads(injected.split(" ", 2)[2])["client_token"] == "secret"
    assert parse_hello_metadata("HELLO client") is None


def test_messaging_tunnel_envelopes() -> None:
    message = tunnel_message_envelope(
        profile_id="p1",
        runtime_instance_id="i1",
        session_id="s1",
        conn_id="c1",
        data="payload",
    )
    assert message.model_dump()["type"] == "msg"
    assert message.data == "payload"
    assert message.agent_session_id == "s1"

    close = tunnel_close_envelope(
        profile_id="p1",
        runtime_instance_id="i1",
        session_id="s1",
        conn_id="c1",
        code=1011,
        reason="failure",
    )
    assert close.code == 1011
    assert close.agent_session_id == "s1"


def test_policy_rules_are_pure_and_stable() -> None:
    assert sanitize_caller("viewer:1") == "viewer:1"
    assert sanitize_caller("bad caller") == "sanitized"
    assert sanitize_caller(None) == "unknown"

    assert should_block_client_verb("r,1")
    assert not should_block_client_verb("HELLO client")

    sanitized = sanitize_settings_message(
        'SETTINGS,{"framerate":30,"video_bitrate":5,"keep":1}'
    )
    assert sanitized == 'SETTINGS,{"keep": 1}'
    assert sanitize_settings_message('SETTINGS,"not-a-dict"') is None
    assert sanitize_settings_message("HELLO client") == "HELLO client"


def test_runtime_view_helpers() -> None:
    runtime = ProfileRuntime(
        profile_id="p1",
        desired_state="running",
        observed_state="error",
        runtime_instance_id="i1",
        config_version=3,
        failure_count=2,
        restart_blocked=True,
        last_exit_event_id="exit_1",
        updated_at="2026-11-01T00:00:00+00:00",
    )
    coordinator = SimpleNamespace(get_last_error=lambda profile_id: "boom")

    response = make_runtime_response(runtime, coordinator)

    assert response.profile_id == "p1"
    assert response.last_coordinator_error == "boom"
    assert response.updated_at == runtime.updated_at
    assert make_runtime_response(runtime).last_coordinator_error is None
    assert resolve_operation_id("idem", "x", "query") == "idem"
    assert resolve_operation_id(None, "x", "query") == "x"
    assert resolve_operation_id(None, None, "query") == "query"
    assert resolve_operation_id(None, None, None) is None
