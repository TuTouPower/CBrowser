"""Internal Supervisor RPC must authenticate over an actual HTTP process."""

import importlib.util
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

_auth_path = Path(__file__).resolve().parents[1] / "fixtures" / "api_auth.py"
_auth_spec = importlib.util.spec_from_file_location("api_auth", _auth_path)
_auth_mod = importlib.util.module_from_spec(_auth_spec)
sys.modules["api_auth"] = _auth_mod
_auth_spec.loader.exec_module(_auth_mod)
create_auth_context = _auth_mod.create_auth_context


@pytest.fixture
def supervisor_api(tmp_path: Path):
    token = secrets.token_urlsafe(32)
    token_file = tmp_path / "supervisor_token"
    token_file.write_text(token)
    token_file.chmod(0o600)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    auth_ctx = create_auth_context(tmp_path, origin=f"http://127.0.0.1:{port}")
    env = dict(os.environ)
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        env.pop(name, None)
    root = Path(__file__).resolve().parents[2]
    env.update(
        PYTHONPATH=str(root / "src/backend"),
        PYTHONDONTWRITEBYTECODE="1",
        TMPDIR=str(tmp_path),
        CBROWSER_DB_PATH=str(tmp_path / "control.db"),
        CBROWSER_SUPERVISOR_TOKEN_FILE=str(token_file),
        **auth_ctx.env,
    )
    with (tmp_path / "server.log").open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "cbrowser.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=root,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", trust_env=False
            ) as client:
                for _ in range(100):
                    try:
                        if client.get("/api/v1/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if process.poll() is not None:
                        pytest.fail("isolated API process exited before readiness")
                    time.sleep(0.1)
                else:
                    pytest.fail("isolated API process did not become ready")
                auth_headers = auth_ctx.login_sync(f"http://127.0.0.1:{port}", client)
                client.headers.update(auth_headers)
                yield client, token
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def test_internal_supervisor_rpc_rejects_unauthorized_and_accepts_file_token(
    supervisor_api,
):
    client, token = supervisor_api
    path = "/api/v1/internal/supervisor/health"
    for authorization in (None, "Bearer " + secrets.token_urlsafe(32)):
        headers = {"Authorization": authorization} if authorization else {}
        response = client.get(path, headers=headers)
        assert response.status_code == 401
        assert token not in response.text
        assert response.headers["www-authenticate"] == "Bearer"
    response = client.get(path, headers={"Authorization": "Bearer " + token})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_authenticated_manual_retry_resets_persistent_failure_once(supervisor_api):
    client, token = supervisor_api
    profile = client.post("/api/v1/profiles", json={"name": "manual_retry"}).json()[
        "id"
    ]
    prefix = "/api/v1/internal/supervisor"
    headers = {"Authorization": "Bearer " + token}
    intent = prefix + f"/profiles/{profile}/runtime/desired-state"
    assert client.patch(intent, json={"desired_state": "running"}).status_code == 401

    def fail(instance):
        bound = client.post(
            prefix + "/runtimes/bind",
            params={"profile_id": profile},
            headers=headers,
            json={"runtime_instance_id": instance, "config_version": 1},
        )
        assert bound.status_code == 200
        response = client.post(
            prefix + "/runtimes/events",
            headers=headers,
            json={
                "event_id": "failure_" + instance,
                "profile_id": profile,
                "runtime_instance_id": instance,
                "event_type": "exit",
                "exit_code": 137,
                "exit_reason": "crash",
                "config_version": 1,
            },
        )
        assert response.status_code == 200

    fail("first")
    request_headers = dict(headers, **{"Idempotency-Key": "manual_retry_operation"})
    retry = client.patch(
        intent, headers=request_headers, json={"desired_state": "running"}
    )
    assert retry.status_code == 200
    assert retry.json()["failure_count"] == 0
    assert not retry.json()["restart_blocked"]
    fail("second")
    replay = client.patch(
        intent, headers=request_headers, json={"desired_state": "running"}
    )
    assert replay.status_code == 200
    assert replay.json()["failure_count"] == 1


def test_authenticated_rpc_replay_does_not_cancel_new_running_intent(supervisor_api):
    client, token = supervisor_api
    created = client.post("/api/v1/profiles", json={"name": "internal_rpc_profile"})
    assert created.status_code == 201
    profile_id = created.json()["id"]
    prefix = "/api/v1/internal/supervisor"
    headers = {"Authorization": "Bearer " + token}
    assert client.get(prefix + "/profiles").status_code == 401
    profiles = client.get(prefix + "/profiles", headers=headers)
    assert profiles.status_code == 200
    assert profile_id in {item["id"] for item in profiles.json()}
    snapshot = client.get(
        prefix + f"/profiles/{profile_id}/versions/1", headers=headers
    )
    assert snapshot.status_code == 200
    assert snapshot.json()["profile_id"] == profile_id
    desired_path = f"/api/v1/profiles/{profile_id}/runtime/desired-state"
    desired = client.patch(
        desired_path,
        json={"desired_state": "running"},
        headers={"Idempotency-Key": "rpc_intent_1"},
    )
    assert desired.status_code == 200
    bound = client.post(
        prefix + "/runtimes/bind",
        params={"profile_id": profile_id},
        headers=headers,
        json={"runtime_instance_id": "rpc_instance_1", "config_version": 1},
    )
    assert bound.status_code == 200
    event = {
        "event_id": "rpc_event_1",
        "profile_id": profile_id,
        "runtime_instance_id": "rpc_instance_1",
        "event_type": "exit",
        "exit_code": 0,
        "exit_reason": "normal",
        "config_version": 1,
    }
    first = client.post(prefix + "/runtimes/events", headers=headers, json=event)
    assert first.status_code == 200
    stopped = client.get(prefix + f"/profiles/{profile_id}/runtime", headers=headers)
    assert stopped.json()["desired_state"] == "stopped"
    restarted = client.patch(
        desired_path,
        json={"desired_state": "running"},
        headers={"Idempotency-Key": "rpc_intent_2"},
    )
    assert restarted.status_code == 200
    duplicate = client.post(prefix + "/runtimes/events", headers=headers, json=event)
    assert duplicate.status_code == 200
    runtime = client.get(prefix + f"/profiles/{profile_id}/runtime", headers=headers)
    assert runtime.status_code == 200
    assert runtime.json()["desired_state"] == "running"
    assert runtime.json()["last_exit_event_id"] == "rpc_event_1"
