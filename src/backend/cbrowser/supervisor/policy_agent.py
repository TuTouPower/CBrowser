"""Persistent per-namespace Policy Agent (t082, ADR 039).

One Agent container joins each Browser/Stream target's network
namespace (``network_mode=container:<exact target ID>``) for the
target's whole lifetime and serves the bounded protocol defined in
:mod:`cbrowser.supervisor.policy_agent_protocol` over a Unix socket
that only the Supervisor and this Agent can see.  It replaces the
one-shot policy helper containers: steady-state inspection no longer
creates or destroys a container per scan, and DNS resolution happens
inside the target namespace without ``docker exec``.

The Agent holds exactly one capability (NET_ADMIN), runs with a
read-only root, and mounts nothing but its own control directory: no
Docker socket, no Profile data, no fonts, no artifacts, no proxy
credentials.  Its only inputs are protocol requests fenced by the
identity it was created for; its only effects are iptables operations
and DNS lookups inside the joined namespace.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
import socketserver
from pathlib import Path

from cbrowser.supervisor.network_policy import (
    NetworkPolicySpec,
    apply_policy,
    install_fail_closed,
    replace_policy,
    verify_fail_closed,
    verify_policy,
)
from cbrowser.supervisor.policy_agent_protocol import (
    MAX_MESSAGE_BYTES,
    PolicyAgentIdentity,
    PolicyAgentRequest,
    PolicyAgentResponse,
    policy_spec_digest,
)

logger = logging.getLogger("cbrowser.supervisor.policy_agent")

_REQUEST_TIMEOUT_SEC = 30.0


class PolicyAgentExecutor:
    """Namespace effects of the Agent; replaceable in tests.

    The production executor drives the shared rule library
    (:mod:`cbrowser.supervisor.network_policy`) in the Agent's own
    process, which lives in the target's network namespace.
    """

    def resolve(self, hostname: str, port: int) -> list[str]:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        addresses = sorted(
            {str(ipaddress.ip_address(info[4][0])) for info in infos}
        )
        if not addresses:
            raise RuntimeError("resolution returned no addresses")
        return addresses

    def install(self, spec: NetworkPolicySpec, *, replace: bool) -> None:
        if replace:
            replace_policy(spec)
        else:
            apply_policy(spec)
        if not verify_policy(spec):
            raise RuntimeError("installed policy does not verify")

    def inspect(self, spec: NetworkPolicySpec) -> bool:
        return verify_policy(spec)

    def fail_close(self) -> bool:
        install_fail_closed()
        return verify_fail_closed()


class PolicyAgent:
    """Protocol state machine: identity + revision fencing over an executor."""

    def __init__(
        self,
        identity: PolicyAgentIdentity,
        executor: PolicyAgentExecutor | None = None,
    ) -> None:
        self.identity = identity
        self.executor = executor or PolicyAgentExecutor()
        self.applied_revision = 0
        self.applied_digest: str | None = None

    @staticmethod
    def _error(request_id: str, code: str) -> PolicyAgentResponse:
        return PolicyAgentResponse(request_id=request_id, ok=False, error_code=code)

    def handle(self, raw: bytes) -> bytes:
        """Handle one raw request line; always returns one response line."""
        response = self._dispatch(raw)
        return (response.model_dump_json() + "\n").encode("utf-8")

    def _dispatch(self, raw: bytes) -> PolicyAgentResponse:
        if len(raw) > MAX_MESSAGE_BYTES:
            return self._error("unknown", "request_too_large")
        try:
            request = PolicyAgentRequest.model_validate_json(raw)
        except Exception:  # noqa: BLE001 - any malformed input is one outcome
            return self._error("unknown", "invalid_request")
        if request.identity != self.identity:
            return self._error(request.request_id, "identity_mismatch")
        handler = {
            "health": self._op_health,
            "resolve": self._op_resolve,
            "install": self._op_install,
            "inspect": self._op_inspect,
            "fail_close": self._op_fail_close,
        }[request.op]
        try:
            return handler(request)
        except Exception as exc:  # noqa: BLE001 - executor failures are typed, never leaked
            logger.warning(
                "Policy agent op failed: op=%s error_type=%s",
                request.op,
                type(exc).__name__,
            )
            return self._error(request.request_id, "execution_failed")

    def _op_health(self, request: PolicyAgentRequest) -> PolicyAgentResponse:
        return PolicyAgentResponse(
            request_id=request.request_id,
            ok=True,
            result={
                "identity": self.identity.model_dump(mode="json"),
                "policy_revision": self.applied_revision,
                "spec_digest": self.applied_digest,
            },
        )

    def _op_resolve(self, request: PolicyAgentRequest) -> PolicyAgentResponse:
        if request.resolve is None:
            return self._error(request.request_id, "invalid_request")
        addresses = self.executor.resolve(
            request.resolve.hostname, request.resolve.port
        )
        return PolicyAgentResponse(
            request_id=request.request_id,
            ok=True,
            result={"addresses": addresses, "port": request.resolve.port},
        )

    def _op_install(self, request: PolicyAgentRequest) -> PolicyAgentResponse:
        if request.spec is None or request.policy_revision is None:
            return self._error(request.request_id, "invalid_request")
        digest = policy_spec_digest(request.spec)
        revision = request.policy_revision
        if revision < self.applied_revision or (
            revision == self.applied_revision and digest != self.applied_digest
        ):
            # Old-revision replay, or a different spec wearing the
            # current revision: never applied.
            return self._error(request.request_id, "stale_revision")
        if revision == self.applied_revision and digest == self.applied_digest:
            # Idempotent retry of the current install: confirm the live
            # rules still match instead of re-applying into a namespace
            # that already carries a policy.
            if not self.executor.inspect(request.spec):
                self.executor.install(request.spec, replace=True)
            return PolicyAgentResponse(
                request_id=request.request_id,
                ok=True,
                result={
                    "policy_revision": revision,
                    "spec_digest": digest,
                    "already_applied": True,
                },
            )
        self.executor.install(request.spec, replace=self.applied_revision > 0)
        self.applied_revision = revision
        self.applied_digest = digest
        return PolicyAgentResponse(
            request_id=request.request_id,
            ok=True,
            result={"policy_revision": revision, "spec_digest": digest},
        )

    def _op_inspect(self, request: PolicyAgentRequest) -> PolicyAgentResponse:
        if request.spec is None or request.policy_revision is None:
            return self._error(request.request_id, "invalid_request")
        if request.policy_revision != self.applied_revision:
            return self._error(request.request_id, "revision_mismatch")
        matches = self.executor.inspect(request.spec)
        return PolicyAgentResponse(
            request_id=request.request_id,
            ok=True,
            result={
                "matches": matches,
                "policy_revision": self.applied_revision,
                "spec_digest": self.applied_digest,
            },
        )

    def _op_fail_close(self, request: PolicyAgentRequest) -> PolicyAgentResponse:
        confirmed = self.executor.fail_close()
        return PolicyAgentResponse(
            request_id=request.request_id,
            ok=confirmed,
            error_code=None if confirmed else "fail_close_unconfirmed",
            result={"confirmed": confirmed},
        )


# ---------------------------------------------------------------------------
# Transport: threaded Unix-socket server, one request per connection.
# ---------------------------------------------------------------------------


class _Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        agent: PolicyAgent = self.server.agent  # type: ignore[attr-defined]
        self.request.settimeout(_REQUEST_TIMEOUT_SEC)
        raw = b""
        try:
            while b"\n" not in raw and len(raw) <= MAX_MESSAGE_BYTES:
                chunk = self.request.recv(8192)
                if not chunk:
                    break
                raw += chunk
        except OSError:
            return
        line = raw.split(b"\n", 1)[0]
        try:
            self.request.sendall(agent.handle(line))
        except OSError:
            pass


class _Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: str, agent: PolicyAgent) -> None:
        self.agent = agent
        super().__init__(address, _Handler)


def identity_from_environment(
    env: dict[str, str] | None = None,
) -> PolicyAgentIdentity:
    """The Agent's bound identity comes only from its creation environment."""
    env = env if env is not None else dict(os.environ)
    return PolicyAgentIdentity(
        deployment_id=env["CBROWSER_POLICY_AGENT_DEPLOYMENT_ID"],
        profile_id=env["CBROWSER_POLICY_AGENT_PROFILE_ID"],
        runtime_instance_id=env["CBROWSER_POLICY_AGENT_RUNTIME_INSTANCE_ID"],
        config_version=int(env["CBROWSER_POLICY_AGENT_CONFIG_VERSION"]),
        role=env["CBROWSER_POLICY_AGENT_ROLE"],  # type: ignore[arg-type]
        target_container_id=env["CBROWSER_POLICY_AGENT_TARGET_CONTAINER_ID"],
    )


def serve_forever(socket_path: Path, agent: PolicyAgent) -> None:
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    # The slot directory belongs to exactly this Agent instance; a stale
    # socket file inside it is its own predecessor's, never a peer's.
    socket_path.unlink(missing_ok=True)
    server = _Server(str(socket_path), agent)
    try:
        os.chmod(socket_path, 0o660)
        server.serve_forever()
    finally:
        server.server_close()
        socket_path.unlink(missing_ok=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    identity = identity_from_environment()
    socket_path = Path(
        os.environ.get(
            "CBROWSER_POLICY_AGENT_SOCKET",
            "/run/cbrowser_policy_agent/agent.sock",
        )
    )
    logger.info(
        "Policy agent serving: profile=%s role=%s target=%s",
        identity.profile_id,
        identity.role,
        identity.target_container_id[:12],
    )
    serve_forever(socket_path, PolicyAgent(identity))


if __name__ == "__main__":
    main()
