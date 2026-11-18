"""t083: steady-state probe counting rules and health migration shape.

The probe's aggregation core is pure: exec_create counts once,
exec_start/exec_die are stage events of the same execution, the
probe's own measurement execs are excluded from the stack count, and
policy churn counts helper/Agent create+destroy only.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_probe():
    spec = importlib.util.spec_from_file_location(
        "steady_state_probe", REPO_ROOT / "scripts" / "steady_state_probe.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _event(action: str, *, cid: str = "c1", name: str = "cbrowser-api", **labels):
    attrs = {"name": name, "com.cbrowser.prefix": "cbrowser", **labels}
    return {
        "Type": "container",
        "Action": action,
        "Actor": {"ID": cid, "Attributes": attrs},
    }


def test_exec_create_counts_once_stages_are_separate():
    probe = _load_probe()
    events = [
        _event("exec_create: python3 -c pass"),
        _event("exec_start: python3 -c pass"),
        _event("exec_die: python3 -c pass"),
    ]
    result = probe.aggregate_events(events, prefix="cbrowser")
    assert result["stack_execs"] == 1
    assert result["exec_stage_events"] == 2
    assert result["measurement_execs"] == 0


def test_measurement_execs_are_excluded_from_stack_count():
    probe = _load_probe()
    events = [
        _event(
            "exec_create: cat /proc/1/io",
            **{"com.cbrowser.measurement": "steady-state-probe"},
        ),
        _event("exec_create: python3 -c pass"),
    ]
    result = probe.aggregate_events(events, prefix="cbrowser")
    assert result["stack_execs"] == 1
    assert result["measurement_execs"] == 1


def test_policy_churn_counts_helper_and_agent_create_destroy():
    probe = _load_probe()
    events = [
        _event(
            "create",
            cid="h1",
            name="cbrowser-x-policy",
            **{"com.cbrowser.role": "network-policy"},
        ),
        _event(
            "destroy",
            cid="h1",
            name="cbrowser-x-policy",
            **{"com.cbrowser.role": "network-policy"},
        ),
        _event(
            "create",
            cid="a1",
            name="cbrowser-x-agent",
            **{"com.cbrowser.role": "network-policy-agent"},
        ),
        _event(
            "start",
            cid="b1",
            name="cbrowser-x-browser",
            **{"com.cbrowser.role": "browser"},
        ),
    ]
    result = probe.aggregate_events(events, prefix="cbrowser")
    assert result["policy_helper_churn_events"] == 2
    assert result["policy_agent_churn_events"] == 1
    assert result["stack_execs"] == 0


def test_foreign_stack_events_are_ignored():
    probe = _load_probe()
    events = [
        _event(
            "exec_create: python3 -c pass",
            name="other-api",
            **{"com.cbrowser.prefix": "other"},
        )
    ]
    result = probe.aggregate_events(events, prefix="cbrowser")
    assert result["stack_execs"] == 0


def test_compose_has_no_docker_healthchecks_or_healthy_dependencies():
    compose = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "healthcheck:" not in compose
    assert "service_healthy" not in compose


def test_deploy_waits_on_real_readiness_not_compose_wait():
    deploy = (REPO_ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    assert "service_readiness_probe.py" in deploy
    assert "wait_services_ready" in deploy
    assert "--wait" not in deploy


def test_measurement_exec_ids_match_the_real_exec_id():
    # t083_code_f002: the id follows the colon in "exec_create: <id>";
    # the literal action name must never count as the id.
    probe = _load_probe()
    events = [
        _event("exec_create: abc123deadbeef"),
        _event("exec_create: 999999999999"),
    ]
    result = probe.aggregate_events(
        events, prefix="cbrowser", measurement_exec_ids={"abc123deadbeef"}
    )
    assert result["measurement_execs"] == 1
    assert result["stack_execs"] == 1


def test_run_probe_event_window_uses_epoch_seconds(monkeypatch):
    # t083_code_f001: Docker parses a naive "%Y-%m-%dT%H:%M:%S" string
    # in the client's local timezone, which would shift the sampled
    # window by the host offset (8 h on a UTC+8 Mac).  Epoch seconds
    # are unambiguous everywhere.
    probe = _load_probe()
    seen: list[list[str]] = []

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(argv, **kwargs):
        seen.append(list(argv))
        return _Result()

    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    result = probe.run_probe(prefix="cbrowser", duration=0, with_rchar=False)
    events_call = next(call for call in seen if "events" in call)
    since = events_call[events_call.index("--since") + 1]
    until = events_call[events_call.index("--until") + 1]
    assert since.isdigit() and until.isdigit()
    assert int(until) >= int(since)
    assert result["window_epoch"] == {
        "since": int(since),
        "until": int(until),
    }


def test_docker_failure_is_loud_not_a_clean_window(monkeypatch):
    # t083_code_f003: a failed collection must never surface as an
    # all-zero steady-state report with exit 0.
    probe = _load_probe()

    class _Result:
        returncode = 1
        stdout = ""
        stderr = "Cannot connect to the Docker daemon"

    monkeypatch.setattr(
        probe.subprocess, "run", lambda argv, **kwargs: _Result()
    )
    with pytest.raises(probe.DockerCommandError, match="Docker daemon"):
        probe.run_probe(prefix="cbrowser", duration=0, with_rchar=False)
    assert (
        probe.main(["--prefix", "cbrowser", "--duration", "0"]) == 2
    )
