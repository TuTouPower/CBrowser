"""Internal Supervisor RPC must authenticate over an actual HTTP process."""

import secrets




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
            prefix + "/runtimes/observed",
            params={"profile_id": profile},
            headers=headers,
            json={
                "runtime_instance_id": instance,
                "observed_state": "error",
                "reason": "container_exit",
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
    observed = client.post(
        prefix + "/runtimes/observed",
        params={"profile_id": profile_id},
        headers=headers,
        json={
            "runtime_instance_id": "rpc_instance_1",
            "observed_state": "stopped",
            "reason": "normal_exit",
            "config_version": 1,
        },
    )
    assert observed.status_code == 200
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
