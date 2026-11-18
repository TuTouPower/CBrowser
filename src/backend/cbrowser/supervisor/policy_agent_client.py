"""Supervisor-side client for the per-namespace Policy Agent (t082).

Synchronous by design: every DockerAdapter policy call site already
runs on a worker thread (``asyncio.to_thread``) or in a synchronous
adapter method, so the client is a plain blocking Unix-socket client
with a hard timeout.  Transport problems raise
:class:`PolicyAgentUnavailable`; a well-formed refusal from the Agent
raises :class:`PolicyAgentRejected` carrying the Agent's stable error
code.  Neither exception ever carries request payloads or credentials
(the protocol has no credential fields to begin with).
"""

from __future__ import annotations

import ipaddress
import socket
import uuid
from pathlib import Path
from typing import Any

from cbrowser.supervisor.network_policy import NetworkPolicySpec
from cbrowser.supervisor.policy_agent_protocol import (
    MAX_MESSAGE_BYTES,
    PolicyAgentIdentity,
    PolicyAgentRequest,
    PolicyAgentResponse,
    ResolveRequest,
)

DEFAULT_TIMEOUT_SEC = 15.0


class PolicyAgentUnavailable(Exception):
    """The Agent could not be reached or answered garbage."""


class PolicyAgentRejected(Exception):
    """The Agent refused the request with a stable error code."""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class PolicyAgentClient:
    """One Agent endpoint: a socket path plus the identity it must fence."""

    def __init__(
        self,
        socket_path: Path | str,
        identity: PolicyAgentIdentity,
        *,
        timeout: float = DEFAULT_TIMEOUT_SEC,
    ) -> None:
        self.socket_path = str(socket_path)
        self.identity = identity
        self.timeout = timeout

    # -- transport ---------------------------------------------------------

    def _roundtrip(self, request: PolicyAgentRequest) -> PolicyAgentResponse:
        payload = (request.model_dump_json() + "\n").encode("utf-8")
        if len(payload) > MAX_MESSAGE_BYTES:
            raise PolicyAgentUnavailable("policy agent request exceeds size bound")
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                conn.settimeout(self.timeout)
                conn.connect(self.socket_path)
                conn.sendall(payload)
                raw = b""
                while b"\n" not in raw:
                    chunk = conn.recv(8192)
                    if not chunk:
                        break
                    raw += chunk
                    if len(raw) > MAX_MESSAGE_BYTES:
                        raise PolicyAgentUnavailable(
                            "policy agent response exceeds size bound"
                        )
        except PolicyAgentUnavailable:
            raise
        except OSError as exc:
            raise PolicyAgentUnavailable(
                f"policy agent transport failed: {type(exc).__name__}"
            ) from None
        try:
            response = PolicyAgentResponse.model_validate_json(
                raw.split(b"\n", 1)[0]
            )
        except Exception:  # noqa: BLE001 - malformed answer is unavailability
            raise PolicyAgentUnavailable(
                "policy agent returned a malformed response"
            ) from None
        if response.request_id != request.request_id:
            raise PolicyAgentUnavailable("policy agent response id mismatch")
        return response

    def _call(
        self,
        op: str,
        *,
        policy_revision: int | None = None,
        spec: NetworkPolicySpec | None = None,
        resolve: ResolveRequest | None = None,
    ) -> dict[str, Any]:
        request = PolicyAgentRequest(
            request_id=uuid.uuid4().hex,
            op=op,  # type: ignore[arg-type]
            identity=self.identity,
            policy_revision=policy_revision,
            spec=spec,
            resolve=resolve,
        )
        response = self._roundtrip(request)
        if not response.ok:
            raise PolicyAgentRejected(response.error_code or "rejected")
        return response.result

    # -- operations --------------------------------------------------------

    def health(self) -> dict[str, Any]:
        return self._call("health")

    def resolve(self, hostname: str, port: int) -> list[tuple[str, int]]:
        result = self._call(
            "resolve", resolve=ResolveRequest(hostname=hostname, port=port)
        )
        addresses = result.get("addresses")
        if not isinstance(addresses, list) or not addresses:
            raise PolicyAgentUnavailable("policy agent resolve returned no addresses")
        resolved: list[tuple[str, int]] = []
        for address in addresses:
            # A resolve receipt is only meaningful as IP literals; a
            # malformed or hostile receipt is an availability failure,
            # never a value that reaches policy derivation.
            try:
                literal = ipaddress.ip_address(str(address))
            except ValueError:
                raise PolicyAgentUnavailable(
                    "policy agent resolve returned a non-IP address"
                ) from None
            resolved.append((str(literal), port))
        return resolved

    def install(self, spec: NetworkPolicySpec, policy_revision: int) -> dict[str, Any]:
        return self._call("install", policy_revision=policy_revision, spec=spec)

    def inspect(self, spec: NetworkPolicySpec, policy_revision: int) -> bool:
        result = self._call("inspect", policy_revision=policy_revision, spec=spec)
        return result.get("matches") is True

    def fail_close(self) -> bool:
        try:
            result = self._call("fail_close")
        except PolicyAgentRejected as exc:
            if exc.error_code == "fail_close_unconfirmed":
                return False
            raise
        return result.get("confirmed") is True
