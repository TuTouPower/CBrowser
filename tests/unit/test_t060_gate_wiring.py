"""Execute the gate with PATH-injected commands, including failure mutations."""

from __future__ import annotations

import json

import pytest

from scripts.check_gate_count import MINIMUM_CASES, check_count
from tests.unit.test_t028_run_gates_evidence import _run_gates, _stub_log


@pytest.mark.parametrize("suite", list(MINIMUM_CASES))
def test_suite_below_baseline_fails(suite):
    assert not check_count(suite, MINIMUM_CASES[suite] - 1)
    assert check_count(suite, MINIMUM_CASES[suite])


def _assert_protocol_before_suites(log):
    lines = log.splitlines()
    export_supervisor = next(
        i
        for i, line in enumerate(lines)
        if "scripts/export_supervisor_protocol.py" in line
    )
    export_stream = next(
        i for i, line in enumerate(lines) if "scripts/export_stream_protocol.py" in line
    )
    check_api = next(i for i, line in enumerate(lines) if "npm run check:api" in line)
    requirements = next(
        i for i, line in enumerate(lines) if line.startswith("uv export")
    )
    unit = next(i for i, line in enumerate(lines) if "pytest tests/unit" in line)
    integration = next(
        i for i, line in enumerate(lines) if "pytest tests/integration" in line
    )
    assert (
        export_supervisor
        < export_stream
        < check_api
        < requirements
        < unit
        < integration
    )
    assert not any("npm run design:tokens" in line for line in lines)
    assert not any("--collect-only" in line and "tests/unit" in line for line in lines)


def test_runtime_order_and_order_mutation_are_observable(tmp_path):
    result = _run_gates(
        tmp_path, {"CBROWSER_GATE_EVIDENCE_DIR": str(tmp_path / "evidence")}
    )
    assert result.returncode == 0, result.stdout + result.stderr
    log = _stub_log(tmp_path)
    _assert_protocol_before_suites(log)
    # Moving the prerequisite after unit changes the observable call trace
    # and must invalidate this oracle (the old substring assertions passed).
    lines = log.splitlines()
    prior = [
        line
        for line in lines
        if "export_supervisor_protocol.py" in line
        or "export_stream_protocol.py" in line
        or "npm run check:api" in line
    ]
    later = [line for line in lines if line not in prior]
    with pytest.raises(AssertionError):
        _assert_protocol_before_suites("\n".join(later + prior))


def test_protocol_failure_keeps_complete_evidence(tmp_path):
    evidence = tmp_path / "evidence"
    result = _run_gates(
        tmp_path,
        {
            "CBROWSER_GATE_EVIDENCE_DIR": str(evidence),
            "GATE_STUB_NPM_FAIL": "check:api",
        },
    )
    assert result.returncode != 0
    manifest = json.loads((evidence / "manifest.json").read_text())
    assert manifest["suites"][0]["name"] == "protocol_drift_check"
    assert manifest["suites"][0]["exit_code"] != 0
    assert {entry["name"] for entry in manifest["suites"]} >= {
        "unit",
        "integration",
        "frontend_test",
        "frontend_build",
    }
    assert not manifest["all_passed"]


def test_missing_image_packages_is_skipped_and_full_gate_fails(tmp_path):
    evidence = tmp_path / "evidence"
    env = {"CBROWSER_GATE_EVIDENCE_DIR": str(evidence), "CBROWSER_RUN_E2E": "1"}
    for name in (
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_STREAM_TEST_IMAGE",
        "CBROWSER_GATEWAY_IMAGE",
        "CBROWSER_SUPERVISOR_TEST_IMAGE",
        "CBROWSER_API_TEST_IMAGE",
    ):
        env[name] = ""
    result = _run_gates(tmp_path, env)
    assert result.returncode != 0
    manifest = json.loads((evidence / "manifest.json").read_text())
    packages = next(
        entry for entry in manifest["suites"] if entry["name"] == "image_packages"
    )
    assert packages["status"] == "skipped"
    assert not manifest["all_passed"]


def test_collected_count_below_minimum_rejects_gate(tmp_path):
    evidence = tmp_path / "evidence"
    result = _run_gates(
        tmp_path,
        {"CBROWSER_GATE_EVIDENCE_DIR": str(evidence), "GATE_STUB_CASE_COUNT": "1"},
    )
    assert result.returncode != 0
    manifest = json.loads((evidence / "manifest.json").read_text())
    assert not manifest["all_passed"]
    for name in ("contract", "unit", "integration"):
        assert (
            next(s for s in manifest["suites"] if s["name"] == name)["exit_code"] != 0
        )
        assert "below minimum" in (evidence / "logs" / (name + ".log")).read_text()


def test_mutated_script_prerequisite_after_backend_fails_order_oracle(
    tmp_path, monkeypatch
):
    import shutil
    import subprocess

    from tests.unit import test_t028_run_gates_evidence as harness

    source = harness.REPO_ROOT
    clone = tmp_path / "repo"
    clone.mkdir()
    for name in ("scripts", "src/backend", "config/docker", "schemas"):
        shutil.copytree(
            source / name,
            clone / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    fixtures = clone / "tests/fixtures"
    fixtures.mkdir(parents=True)
    shutil.copy2(source / "tests/fixtures/e2e_env.py", fixtures)
    subprocess.run(["git", "init", "-q", str(clone)], check=True)
    script = clone / "scripts/run_gates.sh"
    text = script.read_text()
    preflight = (
        '  run_suite protocol_drift_check "protocol_drift_check" protocol_drift_check\n'
    )
    assert preflight in text
    text = text.replace(preflight, "", 1).replace(
        '  wait "$pid_frontend" || true\n',
        '  wait "$pid_frontend" || true\n' + preflight,
    )
    script.write_text(text)
    monkeypatch.setattr(harness, "REPO_ROOT", clone)
    drive = tmp_path / "drive"
    drive.mkdir()
    result = harness._run_gates(
        drive, {"CBROWSER_GATE_EVIDENCE_DIR": str(drive / "evidence")}
    )
    assert result.returncode == 0, result.stdout + result.stderr
    with pytest.raises(AssertionError):
        _assert_protocol_before_suites(harness._stub_log(drive))


def test_two_gate_processes_share_one_cold_venv_without_rebuild(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    shared = tmp_path / "shared_venv"

    def drive(path):
        return _run_gates(
            path,
            {
                "CBROWSER_GATE_VENV": str(shared),
                "CBROWSER_GATE_EVIDENCE_DIR": str(path / "evidence"),
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(drive, (first, second)))
    assert [result.returncode for result in results] == [0, 0], [
        (r.stdout, r.stderr) for r in results
    ]
    calls = _stub_log(first).splitlines() + _stub_log(second).splitlines()
    assert sum(line.startswith("uv venv --clear") for line in calls) == 1
    for path in (first, second):
        assert json.loads((path / "evidence/manifest.json").read_text())["all_passed"]


def test_gate_termination_reaches_suite_process_group(tmp_path):
    import os
    import signal
    import subprocess
    from concurrent.futures import ThreadPoolExecutor

    from wait import wait_until_sync

    evidence = tmp_path / "evidence"
    child_file = tmp_path / "suite-child.pid"
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run_gates, tmp_path, {"CBROWSER_GATE_EVIDENCE_DIR": str(evidence), "GATE_STUB_BLOCK_NPM": "check:api", "GATE_STUB_CHILD_PID": str(child_file)})
        wait_until_sync(child_file.is_file, timeout=10, description="controlled suite process started")
        child_pid = int(child_file.read_text())
        run = json.loads((evidence / "run.json").read_text())
        os.kill(run["pid"], signal.SIGTERM)
        try:
            result = future.result(timeout=10)
        except TimeoutError:
            os.kill(child_pid, signal.SIGTERM)
            future.result(timeout=10)
            raise
        state = subprocess.run(["ps", "-p", str(child_pid), "-o", "stat="], capture_output=True, text=True, check=False)
        alive = state.returncode == 0 and "Z" not in state.stdout
        if alive:
            os.kill(child_pid, signal.SIGTERM)
        assert result.returncode != 0
        assert not alive, "gate returned while a suite subprocess was still running"


@pytest.mark.parametrize("stage", ["venv", "pip"])
def test_bootstrap_failure_replaces_stale_success_evidence(tmp_path, monkeypatch, stage):
    from tests.unit import test_t028_run_gates_evidence as harness

    monkeypatch.setattr(harness, "UV_STUB", harness.UV_STUB.replace(
        "#!/bin/bash\n",
        '#!/bin/bash\nif [ "$1" = "$GATE_STUB_UV_FAIL" ]; then exit 42; fi\n',
        1,
    ))
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "manifest.json").write_text(json.dumps({
        "run_id": "prior-run", "all_passed": True,
        "suites": [{"name": "unit", "exit_code": 0}],
    }))
    result = _run_gates(tmp_path, {
        "CBROWSER_GATE_EVIDENCE_DIR": str(evidence), "GATE_STUB_UV_FAIL": stage,
    })
    assert result.returncode != 0
    manifest = json.loads((evidence / "manifest.json").read_text())
    run = json.loads((evidence / "run.json").read_text())
    assert manifest["all_passed"] is False
    assert manifest["run_id"] == run["run_id"] != "prior-run"
    assert len(manifest["suites"]) == 1
    suite = manifest["suites"][0]
    assert suite["name"] == "environment" and suite["exit_code"] != 0
    assert suite["status"] == "failed"
    assert (evidence / suite["log"]).read_text()
