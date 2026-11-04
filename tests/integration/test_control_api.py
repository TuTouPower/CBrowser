"""t031 control endpoints: real app, real DB, real HTTP (TestClient)."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from cbrowser.api.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def control_env(tmp_path: Path):
    password = secrets.token_urlsafe(32)
    password_file = tmp_path / "admin.txt"
    password_file.write_text(password, encoding="utf-8")
    password_file.chmod(0o600)
    gateway_token = secrets.token_urlsafe(32)
    gateway_file = tmp_path / "gateway.txt"
    gateway_file.write_text(gateway_token, encoding="utf-8")
    gateway_file.chmod(0o600)
    origin = "https://app.cbrowser.local"
    app = create_app(
        db_path=tmp_path / "control.db",
        admin_password_file=password_file,
        gateway_token_file=gateway_file,
        allowed_origins=[origin],
        artifacts_root=tmp_path / "artifacts",
    )
    with TestClient(app, base_url=origin) as client:
        login = client.post("/api/v1/auth/login", json={"password": password})
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Origin": origin}
        profile = client.post(
            "/api/v1/profiles", json={"name": "Control"}, headers=headers
        ).json()
        token = client.post(
            "/api/v1/automation/tokens",
            json={"name": "bot", "profile_ids": [profile["id"]]},
            headers=headers,
        )
        assert token.status_code == 201
        token2 = client.post(
            "/api/v1/automation/tokens",
            json={"name": "bot2", "profile_ids": [profile["id"]]},
            headers=headers,
        )
        assert token2.status_code == 201
        yield {
            "client": client,
            "app": app,
            "headers": headers,
            "profile_id": profile["id"],
            "token": token.json()["token"],
            "token2": token2.json()["token"],
            "gateway_token": gateway_token,
        }


def _control_url(pid: str, suffix: str = "") -> str:
    return f"/api/v1/profiles/{pid}/control{suffix}"


def test_control_claim_handoff_restore_flow(control_env) -> None:
    client = control_env["client"]
    pid = control_env["profile_id"]
    bearer = {"Authorization": f"Bearer {control_env['token']}"}
    bearer2 = {"Authorization": f"Bearer {control_env['token2']}"}

    # Default state: user, generation 0.
    resp = client.get(_control_url(pid))
    assert resp.status_code == 200
    assert resp.json()["owner"] == "user"
    assert resp.json()["generation"] == 0

    # Explicit claim moves to agent.
    resp = client.post(
        _control_url(pid, "/claim"),
        json={"agent_session_id": "exec-1"},
        headers=bearer,
    )
    assert resp.status_code == 200
    assert resp.json()["owner"] == "agent"
    assert resp.json()["generation"] == 1

    # Renewing claim by the same token is a no-op.
    resp = client.post(
        _control_url(pid, "/claim"),
        json={"agent_session_id": "exec-1"},
        headers=bearer,
    )
    assert resp.status_code == 200
    assert resp.json()["generation"] == 1

    # A second token claiming explicitly is a second agent: 409.
    resp = client.post(
        _control_url(pid, "/claim"),
        json={"agent_session_id": "exec-2"},
        headers=bearer2,
    )
    assert resp.status_code == 409

    # Handoff: user, generation 2, reclaim blocked. The Supervisor is
    # not configured in this fixture, so the close stays pending.
    resp = client.post(
        _control_url(pid, "/handoff"),
        json={"reason": "cli_handoff", "agent_session_id": "exec-1"},
        headers=bearer,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["owner"] == "user"
    assert body["generation"] == 2
    assert body["handoff_reason"] == "cli_handoff"
    assert body["agent_reclaim_allowed"] is False
    assert body["pending_supervisor_close"] is True

    # Re-claim while blocked: 409.
    resp = client.post(
        _control_url(pid, "/claim"),
        json={"agent_session_id": "exec-1"},
        headers=bearer,
    )
    assert resp.status_code == 409

    # Explicit human restore returns control to the recorded agent.
    resp = client.post(
        _control_url(pid, "/restore"), headers=control_env["headers"]
    )
    assert resp.status_code == 200
    assert resp.json()["owner"] == "agent"
    assert resp.json()["generation"] == 3


def test_control_handoff_closes_registered_api_tunnels(control_env) -> None:
    client = control_env["client"]
    app = control_env["app"]
    pid = control_env["profile_id"]
    bearer = {"Authorization": f"Bearer {control_env['token']}"}
    closed: list[str] = []

    async def close_fn():
        closed.append("api-tunnel")

    registry = app.state.automation_tunnels
    record = registry.register(pid, close_fn, generation=1)
    assert registry.list_for_profile(pid) != []

    client.post(
        _control_url(pid, "/claim"),
        json={"agent_session_id": "exec-1"},
        headers=bearer,
    )
    resp = client.post(
        _control_url(pid, "/handoff"),
        json={"reason": "permission"},
        headers=bearer,
    )
    assert resp.status_code == 200
    assert closed == ["api-tunnel"]
    assert registry.list_for_profile(pid) == []
    assert record.tunnel_id not in [r.tunnel_id for r in registry.list_for_profile(pid)]


def test_control_endpoints_require_auth(control_env) -> None:
    client = control_env["client"]
    pid = control_env["profile_id"]
    # No session cookie: state and tunnels reject.
    from fastapi.testclient import TestClient as _TC

    with _TC(control_env["app"], base_url="https://app.cbrowser.local") as anon:
        assert anon.get(_control_url(pid)).status_code == 401
        assert anon.get(_control_url(pid, "/tunnels")).status_code == 401
        # No bearer: claim/handoff reject.
        assert (
            anon.post(_control_url(pid, "/claim"), json={}).status_code == 401
        )
        assert (
            anon.post(
                _control_url(pid, "/handoff"), json={"reason": "cli_handoff"}
            ).status_code
            == 401
        )


def test_gateway_takeover_internal_endpoint(control_env) -> None:
    client = control_env["client"]
    pid = control_env["profile_id"]
    url = f"/api/v1/internal/gateway/profiles/{pid}/control/takeover"
    # Missing Gateway credentials: 401.
    resp = client.post(
        url, json={"source": "gateway", "conn_id": "c1", "input_kind": "key"}
    )
    assert resp.status_code == 401
    # Wrong token: 401.
    resp = client.post(
        url,
        json={"source": "gateway", "conn_id": "c1", "input_kind": "key"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert resp.status_code == 401
    # Valid Gateway token: takeover moves a claimed profile to user.
    bearer = {"Authorization": f"Bearer {control_env['token']}"}
    claimed = client.post(
        _control_url(pid, "/claim"),
        json={"agent_session_id": "exec-1"},
        headers=bearer,
    )
    assert claimed.status_code == 200
    resp = client.post(
        url,
        json={"source": "gateway", "conn_id": "c1", "input_kind": "key"},
        headers={
            "Authorization": f"Bearer {control_env['gateway_token']}"
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["owner"] == "user"
    assert body["handoff_reason"] == "human_input"
    # Unknown profile: 404.
    resp = client.post(
        "/api/v1/internal/gateway/profiles/nope/control/takeover",
        json={"source": "gateway"},
        headers={
            "Authorization": f"Bearer {control_env['gateway_token']}"
        },
    )
    assert resp.status_code == 404


def test_runtime_response_carries_control(control_env) -> None:
    client = control_env["client"]
    pid = control_env["profile_id"]
    bearer = {"Authorization": f"Bearer {control_env['token']}"}
    resp = client.get(f"/api/v1/profiles/{pid}/runtime")
    assert resp.status_code == 200
    assert resp.json()["control"]["owner"] == "user"
    client.post(
        _control_url(pid, "/claim"),
        json={"agent_session_id": "exec-1"},
        headers=bearer,
    )
    resp = client.get(f"/api/v1/profiles/{pid}/runtime")
    assert resp.status_code == 200
    assert resp.json()["control"]["owner"] == "agent"
    assert resp.json()["control"]["generation"] == 1


class _StubAttendantCoordinator:
    """Coordinator double serving canned attendant dialogs."""

    def __init__(self) -> None:
        self.held = [
            {
                "target_id": "t1",
                "type": "confirm",
                "message": "Are you sure?",
                "url": "https://x/",
            }
        ]
        self.answered: list[dict] = []

    async def list_attendant_dialogs(self, profile_id: str):
        return list(self.held)

    async def answer_attendant_dialog(
        self, profile_id: str, target_id: str, accept: bool,
        prompt_text=None,
    ):
        for held in self.held:
            if held["target_id"] == target_id:
                self.held.remove(held)
                self.answered.append(
                    {"target_id": target_id, "accept": accept}
                )
                return held
        return None


def test_control_dialogs_peek_and_answer(control_env) -> None:
    client = control_env["client"]
    app = control_env["app"]
    pid = control_env["profile_id"]
    bearer = {"Authorization": f"Bearer {control_env['token']}"}
    bearer2 = {"Authorization": f"Bearer {control_env['token2']}"}
    stub = _StubAttendantCoordinator()
    app.state.coordinator = stub

    # Peek requires the automation token.
    resp = client.get(_control_url(pid, "/dialogs"))
    assert resp.status_code == 401
    # ... and agent control held by that token (t031_code_f001): the
    # default user state refuses dialog actions outright.
    resp = client.get(_control_url(pid, "/dialogs"), headers=bearer)
    assert resp.status_code == 409

    # Claim with the first token, then peek works.
    resp = client.post(
        _control_url(pid, "/claim"),
        json={"agent_session_id": "exec-1"},
        headers=bearer,
    )
    assert resp.status_code == 200
    resp = client.get(_control_url(pid, "/dialogs"), headers=bearer)
    assert resp.status_code == 200
    assert resp.json()["dialogs"][0]["target_id"] == "t1"

    # A second token may not peek or answer the holder's dialog.
    resp = client.get(_control_url(pid, "/dialogs"), headers=bearer2)
    assert resp.status_code == 409
    resp = client.post(
        _control_url(pid, "/dialog-answer"),
        json={"target_id": "t1", "accept": False},
        headers=bearer2,
    )
    assert resp.status_code == 409

    # Answer resolves the held dialog.
    resp = client.post(
        _control_url(pid, "/dialog-answer"),
        json={"target_id": "t1", "accept": False},
        headers=bearer,
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "dismiss"
    assert resp.json()["dialog"]["type"] == "confirm"
    assert stub.answered == [{"target_id": "t1", "accept": False}]

    # Nothing held anymore: peek empty, answer 404.
    resp = client.get(_control_url(pid, "/dialogs"), headers=bearer)
    assert resp.json()["dialogs"] == []
    resp = client.post(
        _control_url(pid, "/dialog-answer"),
        json={"target_id": "t1", "accept": True},
        headers=bearer,
    )
    assert resp.status_code == 404


def test_revoke_token_hands_off_live_control(control_env) -> None:
    """t031_code_f002: revoking a token moves its live control to user
    (identity_invalid) instead of only refusing future connections."""
    client = control_env["client"]
    headers = control_env["headers"]
    pid = control_env["profile_id"]

    created = client.post(
        "/api/v1/automation/tokens",
        json={"name": "doomed", "profile_ids": [pid]},
        headers=headers,
    )
    assert created.status_code == 201
    token_id = created.json()["id"]
    bearer = {"Authorization": f"Bearer {created.json()['token']}"}

    resp = client.post(
        _control_url(pid, "/claim"),
        json={"agent_session_id": "exec-9"},
        headers=bearer,
    )
    assert resp.status_code == 200
    assert resp.json()["owner"] == "agent"

    resp = client.delete(f"/api/v1/automation/tokens/{token_id}", headers=headers)
    assert resp.status_code == 204

    # Control moved to the user with the identity_invalid reason and
    # reclaim blocked; the revoked token is refused outright.
    resp = client.get(_control_url(pid))
    assert resp.status_code == 200
    body = resp.json()
    assert body["owner"] == "user"
    assert body["handoff_reason"] == "identity_invalid"
    assert body["agent_reclaim_allowed"] is False
    resp = client.post(
        _control_url(pid, "/claim"),
        json={"agent_session_id": "exec-9"},
        headers=bearer,
    )
    assert resp.status_code == 401
