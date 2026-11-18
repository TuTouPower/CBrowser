"""Shared in-process Policy Agent rig for unit tests (t082).

The adapter talks to Policy Agents through ``PolicyAgentClient``;
tests substitute the client factory with clients backed by a real
:class:`PolicyAgent` state machine and a fake executor, so protocol
validation, identity fencing and revision rules stay in force while
no socket or Docker daemon is involved.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from cbrowser.supervisor.network_policy import NetworkPolicySpec
from cbrowser.supervisor.policy_agent import PolicyAgent, PolicyAgentExecutor
from cbrowser.supervisor.policy_agent_client import PolicyAgentClient
from cbrowser.supervisor.policy_agent_protocol import (
    PolicyAgentIdentity,
    PolicyAgentResponse,
)


class FakePolicyAgentExecutor(PolicyAgentExecutor):
    """Records effects; resolutions and rule state are scriptable."""

    def __init__(self) -> None:
        self.installed: list[tuple[NetworkPolicySpec, bool]] = []
        self.live_matches = True
        self.fail_close_confirmed = True
        self.resolutions: dict[str, list[str]] = {}
        self.fail_install = False

    def resolve(self, hostname: str, port: int) -> list[str]:
        if hostname in self.resolutions:
            return list(self.resolutions[hostname])
        raise RuntimeError(f"no such host: {hostname}")

    def install(self, spec: NetworkPolicySpec, *, replace: bool) -> None:
        if self.fail_install:
            raise RuntimeError("install failed")
        self.installed.append((spec, replace))
        self.live_matches = True

    def inspect(self, spec: NetworkPolicySpec) -> bool:
        return self.live_matches

    def fail_close(self) -> bool:
        if self.fail_close_confirmed:
            self.live_matches = False
        return self.fail_close_confirmed


class _InProcessClient(PolicyAgentClient):
    """A PolicyAgentClient whose transport is a direct state-machine call."""

    def __init__(self, agent: PolicyAgent) -> None:
        self._agent = agent
        self.identity = agent.identity
        self.socket_path = "<in-process>"
        self.timeout = 5.0

    def _roundtrip(self, request: Any) -> PolicyAgentResponse:
        raw = self._agent.handle(request.model_dump_json().encode("utf-8"))
        return PolicyAgentResponse.model_validate_json(raw)


class PolicyAgentTestRig:
    """Factory + registry of in-process agents, keyed by identity."""

    def __init__(self, executor: FakePolicyAgentExecutor | None = None) -> None:
        self.executor = executor or FakePolicyAgentExecutor()
        self.agents: dict[tuple, PolicyAgent] = {}

    def agent_for(self, identity: PolicyAgentIdentity) -> PolicyAgent:
        key = (
            identity.profile_id,
            identity.runtime_instance_id,
            identity.role,
            identity.target_container_id,
        )
        agent = self.agents.get(key)
        if agent is None:
            agent = PolicyAgent(identity, self.executor)
            self.agents[key] = agent
        return agent

    def factory(self, socket_path: Any, identity: PolicyAgentIdentity):
        return _InProcessClient(self.agent_for(identity))

    def install_on(self, adapter: Any) -> "PolicyAgentTestRig":
        """Point an adapter's client factory at this rig."""
        adapter._policy_agent_client_factory = self.factory
        return self

    def stub_ensure(self, adapter: Any) -> "PolicyAgentTestRig":
        """Replace ensure_policy_agent with an in-process equivalent.

        For tests whose subject is not the agent lifecycle itself:
        the returned handle is registered exactly like the real one,
        so derivation / verify / fail-close flows keep working.
        """
        rig = self

        def _ensure(target, *, profile_id, instance_id, config_version, role):
            identity = adapter._policy_agent_identity(
                profile_id, instance_id, config_version, role, target.id
            )
            from cbrowser.supervisor.docker_adapter import _PolicyAgentHandle

            handle = _PolicyAgentHandle(
                identity=identity,
                client=rig.factory(None, identity),
                agent_container_id=f"fake-agent-{target.id}",
            )
            adapter._policy_agents[target.id] = handle
            return handle

        adapter.ensure_policy_agent = MagicMock(side_effect=_ensure)
        return self
