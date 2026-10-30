"""Policy inputs cannot introduce restore directives or leak rejected data."""

import json
import secrets

import pytest
from cbrowser.supervisor.network_policy import NetworkPolicySpec, main
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
    with pytest.raises(SystemExit):
        main([json.dumps({"role": "browser", "allowed_tcp": [[canary, 443]]})])
    captured = capsys.readouterr()
    assert canary not in captured.out + captured.err + caplog.text
