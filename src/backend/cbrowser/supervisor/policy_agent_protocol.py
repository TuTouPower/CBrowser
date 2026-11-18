"""Bounded UDS protocol between the Supervisor and a Policy Agent (t082).

One Policy Agent lives inside each target network namespace for the
target's whole lifetime (ADR 039).  The protocol is deliberately tiny:
five operations (``health`` / ``resolve`` / ``install`` / ``inspect`` /
``fail_close``), newline-delimited JSON, one request per connection,
and a hard message-size bound.  There is no shell, command, mount or
filesystem-path entry point, and DNS resolution accepts only a
hostname/port pair -- never a credential or a full proxy URL.

Every request carries the full identity the Agent was bound to at
creation (deployment, profile, runtime instance, config version, role
and the exact target Docker container ID) plus, for policy operations,
the policy revision.  The Agent rejects any request whose identity
does not equal its bound identity, and any install whose revision is
not newer than the applied one (an equal revision is only accepted
with an identical spec digest, which makes retries idempotent while
old-revision replays and same-revision spec swaps are refused).
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from cbrowser.supervisor.network_policy import NetworkPolicySpec

MAX_MESSAGE_BYTES = 64 * 1024

PolicyAgentOp = Literal["health", "resolve", "install", "inspect", "fail_close"]

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*$"
)


class PolicyAgentIdentity(BaseModel):
    """The exact target binding a Policy Agent serves."""

    model_config = ConfigDict(extra="forbid")

    deployment_id: str = Field(min_length=1, max_length=128)
    profile_id: str = Field(min_length=1, max_length=128)
    runtime_instance_id: str = Field(min_length=1, max_length=128)
    config_version: int = Field(ge=0)
    role: Literal["browser", "stream"]
    target_container_id: str = Field(min_length=1, max_length=128)


class ResolveRequest(BaseModel):
    """DNS resolution input: a bare hostname and port, nothing else."""

    model_config = ConfigDict(extra="forbid")

    hostname: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, value: str) -> str:
        # An IP literal is a valid resolution input (it resolves to
        # itself, matching the Supervisor's historical behaviour); a
        # DNS name must be a plain hostname -- no scheme, credentials,
        # path, port or whitespace can ride along.
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            pass
        if not _HOSTNAME_RE.match(value):
            raise ValueError("hostname must be a plain DNS name or IP literal")
        return value


class PolicyAgentRequest(BaseModel):
    """One bounded request from the Supervisor to a Policy Agent."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=64)
    op: PolicyAgentOp
    identity: PolicyAgentIdentity
    policy_revision: int | None = Field(default=None, ge=1)
    spec: NetworkPolicySpec | None = None
    resolve: ResolveRequest | None = None


class PolicyAgentResponse(BaseModel):
    """The Agent's answer; ``result`` is op-specific and credential-free."""

    model_config = ConfigDict(extra="forbid")

    request_id: str
    ok: bool
    error_code: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)


def policy_spec_digest(spec: NetworkPolicySpec) -> str:
    """Canonical digest of a policy spec (revision fencing + attestation)."""
    canonical = json.dumps(
        spec.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
