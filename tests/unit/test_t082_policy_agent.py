"""t082: Policy Agent protocol, fencing and client behaviour.

The agent state machine is exercised directly (no Docker, no root):
a fake executor records effects, so identity fencing, revision
replay rules, resolve input validation and failure typing are all
proven against the real protocol models and dispatch.
"""

from __future__ import annotations

import json
import socket
import tempfile
import threading
from pathlib import Path

import pytest

from cbrowser.supervisor.network_policy import NetworkPolicySpec
from cbrowser.supervisor.policy_agent import PolicyAgent, PolicyAgentExecutor
from cbrowser.supervisor.policy_agent_client import (
    PolicyAgentClient,
    PolicyAgentRejected,
    PolicyAgentUnavailable,
)
from cbrowser.supervisor.policy_agent_protocol import (
    PolicyAgentIdentity,
    PolicyAgentRequest,
    ResolveRequest,
    policy_spec_digest,
)

IDENTITY = PolicyAgentIdentity(
    deployment_id="dep-1",
    profile_id="profile-1",
    runtime_instance_id="inst-1",
    config_version=3,
    role="browser",
    target_container_id="target-abc",
)

SPEC = NetworkPolicySpec(
    role="browser",
    allowed_tcp=[("203.0.113.7", 8080)],
    allowed_udp=[],
    proxy_enforced=True,
)


class FakeExecutor(PolicyAgentExecutor):
    def __init__(self) -> None:
        self.installed: list[tuple[NetworkPolicySpec, bool]] = []
        self.live_matches = True
        self.fail_close_confirmed = True
        self.resolutions: dict[str, list[str]] = {}

    def resolve(self, hostname: str, port: int) -> list[str]:
        if hostname in self.resolutions:
            return self.resolutions[hostname]
        raise RuntimeError("no such host")

    def install(self, spec: NetworkPolicySpec, *, replace: bool) -> None:
        self.installed.append((spec, replace))
        self.live_matches = True

    def inspect(self, spec: NetworkPolicySpec) -> bool:
        return self.live_matches

    def fail_close(self) -> bool:
        self.live_matches = False
        return self.fail_close_confirmed


def _request(op: str, **kwargs) -> bytes:
    request = PolicyAgentRequest(
        request_id="req-1", op=op, identity=IDENTITY, **kwargs
    )
    return request.model_dump_json().encode()


def _result(agent: PolicyAgent, raw: bytes) -> dict:
    return json.loads(agent.handle(raw))


def test_health_reports_bound_identity_and_revision() -> None:
    agent = PolicyAgent(IDENTITY, FakeExecutor())
    response = _result(agent, _request("health"))
    assert response["ok"] is True
    assert response["result"]["identity"]["target_container_id"] == "target-abc"
    assert response["result"]["policy_revision"] == 0


def test_identity_mismatch_is_rejected_for_every_op() -> None:
    # Every identity field is fenced, for every op: a request whose
    # deployment / profile / instance / config version / role / target
    # differs in any single field is rejected before any effect.
    op_kwargs = {
        "health": {},
        "resolve": {"resolve": {"hostname": "example.com", "port": 443}},
        "install": {"spec": SPEC, "policy_revision": 1},
        "inspect": {"spec": SPEC, "policy_revision": 1},
        "fail_close": {},
    }
    forged_values = {
        "deployment_id": "other-deployment",
        "profile_id": "other-profile",
        "runtime_instance_id": "other-instance",
        "config_version": 99,
        "role": "stream",
        "target_container_id": "other-target",
    }
    for field, value in forged_values.items():
        for op, kwargs in op_kwargs.items():
            executor = FakeExecutor()
            agent = PolicyAgent(IDENTITY, executor)
            forged = PolicyAgentRequest(
                request_id="req-9",
                op=op,
                identity=IDENTITY.model_copy(update={field: value}),
                **kwargs,
            )
            response = _result(agent, forged.model_dump_json().encode())
            assert response["ok"] is False, (field, op)
            assert response["error_code"] == "identity_mismatch", (field, op)
            assert executor.installed == [], (field, op)


def test_client_resolve_rejects_non_ip_receipts() -> None:
    # A resolve receipt carrying a non-IP value is an availability
    # failure (PolicyAgentUnavailable), never a value that reaches
    # policy derivation and never a bare pydantic ValueError.
    from cbrowser.supervisor.policy_agent_client import (
        PolicyAgentClient,
        PolicyAgentUnavailable,
    )

    class _StubClient(PolicyAgentClient):
        def _call(self, op, **kwargs):  # noqa: ANN001, ANN202
            return {"addresses": ["proxy.example.com"]}

    client = _StubClient.__new__(_StubClient)
    with pytest.raises(PolicyAgentUnavailable):
        client.resolve("proxy.example.com", 8080)


def test_install_then_inspect_roundtrip_and_idempotent_retry() -> None:
    executor = FakeExecutor()
    agent = PolicyAgent(IDENTITY, executor)
    installed = _result(agent, _request("install", spec=SPEC, policy_revision=1))
    assert installed["ok"] is True
    assert executor.installed == [(SPEC, False)]
    # Same revision + same digest: idempotent, no second apply.
    retry = _result(agent, _request("install", spec=SPEC, policy_revision=1))
    assert retry["ok"] is True
    assert retry["result"]["already_applied"] is True
    assert len(executor.installed) == 1
    inspected = _result(agent, _request("inspect", spec=SPEC, policy_revision=1))
    assert inspected["result"]["matches"] is True


def test_old_revision_replay_and_same_revision_swap_are_rejected() -> None:
    executor = FakeExecutor()
    agent = PolicyAgent(IDENTITY, executor)
    _result(agent, _request("install", spec=SPEC, policy_revision=2))
    replay = _result(agent, _request("install", spec=SPEC, policy_revision=1))
    assert replay["error_code"] == "stale_revision"
    other = NetworkPolicySpec(
        role="browser", allowed_tcp=[("198.51.100.9", 443)], proxy_enforced=True
    )
    swap = _result(agent, _request("install", spec=other, policy_revision=2))
    assert swap["error_code"] == "stale_revision"
    # Inspect with a non-current revision is fenced too.
    fenced = _result(agent, _request("inspect", spec=SPEC, policy_revision=1))
    assert fenced["error_code"] == "revision_mismatch"
    assert len(executor.installed) == 1


def test_refresh_install_replaces_and_bumps_revision() -> None:
    executor = FakeExecutor()
    agent = PolicyAgent(IDENTITY, executor)
    _result(agent, _request("install", spec=SPEC, policy_revision=1))
    refreshed = NetworkPolicySpec(
        role="browser", allowed_tcp=[("203.0.113.8", 8080)], proxy_enforced=True
    )
    response = _result(
        agent, _request("install", spec=refreshed, policy_revision=2)
    )
    assert response["ok"] is True
    assert executor.installed[-1] == (refreshed, True)
    assert agent.applied_digest == policy_spec_digest(refreshed)


def test_fail_close_reports_confirmation() -> None:
    executor = FakeExecutor()
    agent = PolicyAgent(IDENTITY, executor)
    response = _result(agent, _request("fail_close"))
    assert response["ok"] is True
    assert response["result"]["confirmed"] is True
    executor.fail_close_confirmed = False
    response = _result(agent, _request("fail_close"))
    assert response["ok"] is False
    assert response["error_code"] == "fail_close_unconfirmed"


def test_resolve_accepts_hostname_and_ip_literal_only() -> None:
    executor = FakeExecutor()
    executor.resolutions["proxy.example.com"] = ["203.0.113.7"]
    agent = PolicyAgent(IDENTITY, executor)
    response = _result(
        agent,
        _request(
            "resolve",
            resolve=ResolveRequest(hostname="proxy.example.com", port=8080),
        ),
    )
    assert response["result"]["addresses"] == ["203.0.113.7"]
    # Credentials, URLs, paths and command-shaped input never validate.
    for bad in (
        "user:pass@proxy.example.com",
        "http://proxy.example.com",
        "proxy.example.com/path",
        "proxy example.com",
        "proxy.example.com:8080",
        "$(reboot)",
        "",
    ):
        with pytest.raises(Exception):
            ResolveRequest(hostname=bad, port=8080)


def test_malformed_and_oversized_requests_are_typed() -> None:
    agent = PolicyAgent(IDENTITY, FakeExecutor())
    assert _result(agent, b"not json")["error_code"] == "invalid_request"
    assert _result(agent, b"x" * 70000)["error_code"] == "request_too_large"
    # Extra fields (a smuggled command key) are refused by the schema.
    payload = json.loads(_request("health"))
    payload["command"] = "rm -rf /"
    response = _result(agent, json.dumps(payload).encode())
    assert response["error_code"] == "invalid_request"


def _short_tmp() -> Path:
    # AF_UNIX paths are length-bound; pytest tmp dirs can exceed it.
    return Path(tempfile.mkdtemp(prefix="pa-", dir="/tmp"))


def test_client_roundtrip_over_real_uds() -> None:
    from cbrowser.supervisor.policy_agent import _Server

    executor = FakeExecutor()
    executor.resolutions["proxy.example.com"] = ["203.0.113.7", "2001:db8::7"]
    agent = PolicyAgent(IDENTITY, executor)
    socket_path = _short_tmp() / "agent.sock"
    server = _Server(str(socket_path), agent)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = PolicyAgentClient(socket_path, IDENTITY, timeout=5)
        assert client.health()["policy_revision"] == 0
        resolved = client.resolve("proxy.example.com", 8080)
        assert sorted(resolved) == [
            ("2001:db8::7", 8080),
            ("203.0.113.7", 8080),
        ]
        client.install(SPEC, 1)
        assert client.inspect(SPEC, 1) is True
        assert client.fail_close() is True
        with pytest.raises(PolicyAgentRejected) as excinfo:
            client.inspect(SPEC, 7)
        assert excinfo.value.error_code == "revision_mismatch"
    finally:
        server.shutdown()
        server.server_close()


def test_client_unavailable_when_socket_missing() -> None:
    tmp_path = _short_tmp()
    client = PolicyAgentClient(tmp_path / "absent.sock", IDENTITY, timeout=1)
    with pytest.raises(PolicyAgentUnavailable):
        client.health()
    # And when the peer is a raw socket that never answers protocol.
    raw_path = tmp_path / "raw.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(raw_path))
    listener.listen(1)
    try:
        client = PolicyAgentClient(raw_path, IDENTITY, timeout=1)
        with pytest.raises(PolicyAgentUnavailable):
            client.health()
    finally:
        listener.close()
