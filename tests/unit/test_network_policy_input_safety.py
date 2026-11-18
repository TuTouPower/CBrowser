"""Policy inputs cannot introduce restore directives or leak rejected data.

t082: the one-shot CLI entry point was removed with the temporary
policy helpers; the no-echo property now binds the Policy Agent
protocol surface (invalid requests are answered with a stable error
code and never echo the rejected payload).
"""

import json
import secrets

import pytest
from cbrowser.supervisor.network_policy import NetworkPolicySpec
from cbrowser.supervisor.policy_agent import PolicyAgent
from cbrowser.supervisor.policy_agent_protocol import PolicyAgentIdentity
from pydantic import ValidationError


@pytest.mark.parametrize(
    "endpoint",
    [
        ("fe80::1%eth0\n-A OUTPUT -j ACCEPT", 443),
        ("fe80::1%eth0", 443),
        ("127.0.0.1", True),
    ],
)
def test_policy_rejects_scoped_or_noninteger_endpoint(endpoint):
    with pytest.raises(ValidationError):
        NetworkPolicySpec(role="browser", allowed_tcp=[endpoint])


def test_invalid_policy_diagnostics_do_not_echo_input(capsys, caplog):
    canary = "private_proxy_" + secrets.token_hex(16)
    agent = PolicyAgent(
        PolicyAgentIdentity(
            deployment_id="dep",
            profile_id="profile",
            runtime_instance_id="inst",
            config_version=1,
            role="browser",
            target_container_id="target",
        )
    )
    raw = json.dumps(
        {
            "request_id": "req-canary",
            "op": "install",
            "identity": {
                "deployment_id": "dep",
                "profile_id": "profile",
                "runtime_instance_id": "inst",
                "config_version": 1,
                "role": "browser",
                "target_container_id": "target",
            },
            "policy_revision": 1,
            "spec": {"role": "browser", "allowed_tcp": [[canary, 443]]},
        }
    ).encode()
    response = agent.handle(raw)
    captured = capsys.readouterr()
    assert canary not in response.decode()
    assert canary not in captured.out + captured.err + caplog.text
