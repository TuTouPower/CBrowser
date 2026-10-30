"""Agent credentials must be scoped and depend on an external service key."""

import secrets

import pytest
from cbrowser.supervisor.agent_credentials import AgentCredentials


def test_agent_tokens_are_distinct_for_each_profile_and_runtime(tmp_path):
    key = tmp_path / "agent_key"
    key.write_text(secrets.token_urlsafe(32))
    credentials = AgentCredentials(key)
    token = credentials.token_for("profile_a", "runtime_1")
    assert credentials.verify(token, "profile_a", "runtime_1")
    assert not credentials.verify(token, "profile_b", "runtime_1")
    assert not credentials.verify(token, "profile_a", "runtime_2")
    assert token != key.read_text()


def test_missing_or_short_external_key_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="key"):
        AgentCredentials(tmp_path / "missing")
    key = tmp_path / "short_key"
    key.write_text("short")
    with pytest.raises(ValueError, match="key"):
        AgentCredentials(key)
