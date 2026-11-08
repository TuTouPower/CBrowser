"""Service layer for Network Access settings and recoverable Apply transactions."""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx

from cbrowser.adapters.database.repository import (
    NetworkTransaction,
    ProfileRepository,
)
from cbrowser.domain.models import (
    AppliedNetworkAccessVersion,
    NetworkAccessConfig,
    NetworkAccessSettingsResponse,
    NetworkApplyOperation,
    NetworkApplyPhase,
    utc_now_iso,
)
from cbrowser.gateway.config import NetworkPublicationAuthority
from cbrowser.network_config import (
    CADDYFILE_FILENAME,
    compute_caddyfile_sha256,
    create_default_applied_version,
    derive_origin_whitelist,
    generate_caddyfile,
    write_applied_network_state,
)

logger = logging.getLogger("cbrowser.network_service")


class GatewayPublicationClient:
    def __init__(self, base_url: str, token: Any, client: Any = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = (
            token.get_secret_value()
            if hasattr(token, "get_secret_value")
            else str(token).strip()
        )
        self._client = client or httpx.AsyncClient(
            timeout=10.0, trust_env=False
        )

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}/gateway/v1/network/publication"
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            resp = await self._client.post(url, json=payload, headers=headers)
        except httpx.TransportError as exc:
            raise RuntimeError(
                f"Gateway publication unreachable: {type(exc).__name__}"
            ) from None
        if resp.status_code != 200:
            raise RuntimeError(
                f"Gateway publication failed ({resp.status_code})"
            ) from None
        try:
            body = resp.json()
        except ValueError:
            raise RuntimeError("Gateway publication returned invalid JSON") from None
        if not isinstance(body, dict):
            raise RuntimeError("Gateway publication returned invalid payload")
        return body

    async def prepare(
        self,
        operation_id: str,
        generation: int,
        config_hash: str,
        origins: list[str],
    ) -> dict[str, Any]:
        return await self._post(
            {
                "action": "prepare",
                "operation_id": operation_id,
                "generation": generation,
                "config_hash": config_hash,
                "origins": list(origins),
            }
        )

    async def acknowledge(
        self, operation_id: str, generation: int, config_hash: str
    ) -> dict[str, Any]:
        return await self._post(
            {
                "action": "acknowledge",
                "operation_id": operation_id,
                "generation": generation,
                "config_hash": config_hash,
                "origins": [],
            }
        )

    async def revoke(
        self, operation_id: str, generation: int, config_hash: str
    ) -> dict[str, Any]:
        return await self._post(
            {
                "action": "revoke",
                "operation_id": operation_id,
                "generation": generation,
                "config_hash": config_hash,
                "origins": [],
            }
        )


class _LocalPublicationClient:
    def __init__(self, authority: Any) -> None:
        self._authority = authority

    async def _call(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    async def prepare(
        self,
        operation_id: str,
        generation: int,
        config_hash: str,
        origins: list[str],
    ) -> dict[str, Any]:
        result = await self._call(
            self._authority.authorize(
                operation_id, generation, config_hash, list(origins)
            )
        )
        authorized = (
            result.get("authorized", True) if isinstance(result, dict) else True
        )
        return {
            "published": authorized is not False,
            "source": "local",
            "operation_id": operation_id,
            "generation": generation,
            "config_hash": config_hash,
        }

    async def acknowledge(
        self, operation_id: str, generation: int, config_hash: str
    ) -> dict[str, Any]:
        ack = await self._call(
            self._authority.acknowledge(operation_id, generation, config_hash)
        )
        active = await self._call(self._authority.active())
        payload = dict(ack) if isinstance(ack, dict) else {"acked": False}
        payload["source"] = "local"
        payload["active"] = active
        payload.setdefault("operation_id", operation_id)
        payload.setdefault("generation", generation)
        payload.setdefault("snapshot_hash", config_hash)
        return payload

    async def revoke(
        self, operation_id: str, generation: int, config_hash: str
    ) -> dict[str, Any]:
        result = await self._call(self._authority.revoke(operation_id))
        return {
            "revoked": True,
            "source": "local",
            "operation_id": operation_id,
            "generation": generation,
            "config_hash": config_hash,
            "active": (
                result.get("publication") if isinstance(result, dict) else None
            ),
        }


class NetworkService:
    def __init__(
        self,
        *,
        repo: ProfileRepository,
        auth_service: Any,
        supervisor_client: Any,
        export_dir: Path,
        api_upstream: str = "http://api:8000",
        gateway_upstream: str = "http://gateway:18080",
        on_origins_updated: Any = None,
        gateway: Any = None,
        gateway_client: Any = None,
    ) -> None:
        self.repo = repo
        self.auth_service = auth_service
        self.supervisor_client = supervisor_client
        self.export_dir = export_dir
        self.api_upstream = api_upstream
        self.gateway_upstream = gateway_upstream
        self.on_origins_updated = on_origins_updated
        self.gateway = gateway if gateway is not None else NetworkPublicationAuthority()
        self.publication = (
            gateway_client
            if gateway_client is not None
            else _LocalPublicationClient(self.gateway)
        )
        self._background_tasks: dict[str, asyncio.Task[None]] = {}

    async def get_settings(self) -> NetworkAccessSettingsResponse:
        return await self.repo.get_network_access_settings(self.export_dir)

    async def update_pending_config(self, config: NetworkAccessConfig) -> None:
        await self.repo.save_pending_network_config(config)

    async def get_operation(self, operation_id: str) -> NetworkApplyOperation | None:
        return await self.repo.get_network_operation(operation_id)

    async def apply_configuration(
        self,
        admin_password: str,
        current_request_host: str | None = None,
    ) -> NetworkApplyOperation:
        is_valid = await self.auth_service.verify_admin_password(admin_password)
        if not is_valid:
            raise PermissionError("Invalid admin password")

        current_settings = await self.repo.get_network_access_settings(self.export_dir)
        old_applied = current_settings.applied_version
        target_config = current_settings.pending_config
        target_version_num = old_applied.version + 1
        bind_host = "0.0.0.0" if target_config.lan_access_enabled else "127.0.0.1"

        dummy_ver = AppliedNetworkAccessVersion(
            version=target_version_num,
            config=target_config,
            bind_host=bind_host,
            applied_at=utc_now_iso(),
            caddyfile_sha256="",
            origin_whitelist=[],
        )
        caddy_content = generate_caddyfile(
            dummy_ver,
            api_upstream=self.api_upstream,
            gateway_upstream=self.gateway_upstream,
        )
        caddy_sha = compute_caddyfile_sha256(caddy_content)
        new_version = AppliedNetworkAccessVersion(
            version=target_version_num,
            config=target_config,
            bind_host=bind_host,
            applied_at=utc_now_iso(),
            caddyfile_sha256=caddy_sha,
            origin_whitelist=derive_origin_whitelist(dummy_ver),
        )

        op_id = str(uuid.uuid4())
        new_entry_url = None
        target_port = target_config.https_port
        if target_config.lan_access_enabled and target_config.lan_advertised_ip:
            new_entry_url = f"https://{target_config.lan_advertised_ip}:{target_port}"
        elif not target_config.lan_access_enabled:
            new_entry_url = f"https://127.0.0.1:{target_port}"

        op = NetworkApplyOperation(
            operation_id=op_id,
            target_version=target_version_num,
            phase=NetworkApplyPhase.PENDING,
            new_entry_url=new_entry_url,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        txn = await self.repo.begin_network_transaction(
            operation=op,
            old_applied=old_applied,
            target_applied=new_version,
            candidate_hash=caddy_sha,
        )
        task = asyncio.create_task(
            self._execute_apply(txn, new_version, caddy_content)
        )
        self._background_tasks[op_id] = task
        return op

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    def _component_hash(
        self, result: Any, candidate_hash: str, staging: Path
    ) -> str:
        if isinstance(result, dict) and result.get("caddyfile_sha256"):
            return str(result["caddyfile_sha256"])
        return compute_caddyfile_sha256(staging.read_text(encoding="utf-8"))

    def _prepare_ok(
        self,
        receipt: Any,
        operation_id: str,
        generation: int,
        candidate_hash: str,
    ) -> bool:
        if not isinstance(receipt, dict) or receipt.get("published") is not True:
            return False
        if receipt.get("operation_id") != operation_id:
            return False
        if receipt.get("generation") != generation:
            return False
        if receipt.get("config_hash") != candidate_hash:
            return False
        return True

    def _readiness_ok(
        self,
        ack: Any,
        operation_id: str,
        generation: int,
        candidate_hash: str,
        component_hash: str,
    ) -> bool:
        if not isinstance(ack, dict) or ack.get("acked") is not True:
            return False
        if ack.get("operation_id") != operation_id:
            return False
        if ack.get("generation") != generation:
            return False
        if ack.get("snapshot_hash") != candidate_hash:
            return False
        active = ack.get("active")
        if not isinstance(active, dict):
            return False
        if active.get("operation_id") != operation_id:
            return False
        if active.get("generation") != generation:
            return False
        if active.get("snapshot_hash") != candidate_hash:
            return False
        if component_hash != candidate_hash:
            return False
        return True

    async def _execute_apply(
        self,
        txn: NetworkTransaction,
        new_version: AppliedNetworkAccessVersion,
        caddyfile_content: str,
    ) -> None:
        op_id = txn.operation_id
        generation = txn.execution_generation
        candidate_hash = txn.candidate_hash
        old_applied = AppliedNetworkAccessVersion.model_validate(txn.old_applied)
        self.export_dir.mkdir(parents=True, exist_ok=True)
        staging_caddy = self.export_dir / f"Caddyfile.staging.{op_id}"
        try:
            staging_caddy.write_text(caddyfile_content, encoding="utf-8")
            staging_caddy.chmod(0o644)
            if (
                compute_caddyfile_sha256(staging_caddy.read_text(encoding="utf-8"))
                != candidate_hash
            ):
                raise RuntimeError("candidate snapshot hash mismatch")

            await self.repo.advance_network_transaction(
                op_id,
                transaction_phase="installing",
                phase=NetworkApplyPhase.REBUILDING_CADDY,
                component_hash=candidate_hash,
            )
            prepared = await self.publication.prepare(
                op_id,
                generation,
                candidate_hash,
                list(new_version.origin_whitelist),
            )
            if not self._prepare_ok(
                prepared, op_id, generation, candidate_hash
            ):
                raise RuntimeError("Gateway publication not verifiable")

            rebuild_result = await self.supervisor_client.rebuild_edge(
                target_version=new_version.version,
                bind_host=new_version.bind_host,
                https_port=new_version.config.https_port,
                caddyfile_path=str(staging_caddy),
                operation_id=op_id,
                execution_generation=generation,
                candidate_hash=candidate_hash,
            )
            component_hash = self._component_hash(
                rebuild_result, candidate_hash, staging_caddy
            )
            await self.repo.advance_network_transaction(
                op_id,
                transaction_phase="streams",
                phase=NetworkApplyPhase.REBUILDING_STREAM,
                component_hash=component_hash,
            )

            advertised_ip = (
                new_version.config.lan_advertised_ip
                if new_version.config.lan_access_enabled
                else "127.0.0.1"
            )
            await self.supervisor_client.converge_network_streams(
                target_version=new_version.version,
                bind_host=new_version.bind_host,
                advertised_ip=advertised_ip,
                operation_id=op_id,
                execution_generation=generation,
            )

            await self.repo.advance_network_transaction(
                op_id,
                transaction_phase="verifying",
                phase=NetworkApplyPhase.VERIFYING_READINESS,
            )
            ack = await self.publication.acknowledge(
                op_id, generation, candidate_hash
            )
            if not self._readiness_ok(
                ack,
                op_id,
                generation,
                candidate_hash,
                component_hash,
            ):
                raise RuntimeError("Gateway ACK not verifiable")

            await self.repo.advance_network_transaction(
                op_id,
                gateway_acked=True,
                gateway_generation=generation,
                gateway_hash=candidate_hash,
            )
            committed = await self.repo.commit_network_transaction(
                operation_id=op_id,
                execution_generation=generation,
                gateway_generation=generation,
                gateway_hash=candidate_hash,
            )
            await self._finalize_commit(committed)
            logger.info(
                "Apply operation %s committed to version %d",
                op_id,
                new_version.version,
            )
        except Exception as exc:
            await self._abort(
                op_id,
                generation,
                candidate_hash,
                old_applied,
                exc,
                staging_caddy,
            )

    async def _finalize_commit(self, txn: NetworkTransaction) -> None:
        target = AppliedNetworkAccessVersion.model_validate(txn.target_applied)
        caddy_content = generate_caddyfile(
            target,
            api_upstream=self.api_upstream,
            gateway_upstream=self.gateway_upstream,
        )
        write_applied_network_state(self.export_dir, target, caddy_content)
        staging = self.export_dir / f"Caddyfile.staging.{txn.operation_id}"
        staging.unlink(missing_ok=True)
        if callable(self.on_origins_updated):
            try:
                self.on_origins_updated(target.origin_whitelist)
            except Exception as exc:
                logger.warning(
                    "on_origins_updated callback failed: error_type=%s",
                    type(exc).__name__,
                )

    async def _restore_old(self, txn: NetworkTransaction) -> bool:
        old = (
            AppliedNetworkAccessVersion.model_validate(txn.old_applied)
            if txn.old_applied
            else create_default_applied_version()
        )
        try:
            await self.publication.revoke(
                txn.operation_id, txn.execution_generation, txn.candidate_hash
            )
            await self._maybe_await(
                self.supervisor_client.restore_network_snapshot(
                    operation_id=txn.operation_id,
                    execution_generation=txn.execution_generation,
                    old_version=old.version,
                    bind_host=old.bind_host,
                    https_port=old.config.https_port,
                    caddyfile_sha256=old.caddyfile_sha256,
                    caddyfile_path=str(self.export_dir / CADDYFILE_FILENAME),
                )
            )
            if callable(self.on_origins_updated):
                self.on_origins_updated(list(old.origin_whitelist))
            return True
        except Exception as exc:
            logger.warning(
                "Recovery compensation incomplete for %s: error_type=%s",
                txn.operation_id,
                type(exc).__name__,
            )
            return False

    async def _abort(
        self,
        op_id: str,
        generation: int,
        candidate_hash: str,
        old_applied: AppliedNetworkAccessVersion,
        exc: Exception,
        staging_caddy: Path,
    ) -> None:
        staging_caddy.unlink(missing_ok=True)
        current = await self.repo.get_network_transaction(op_id)
        if current is not None and current.decision == "commit":
            logger.warning(
                "Apply operation %s committed before export; recovery will finalize",
                op_id,
            )
            return
        logger.warning(
            "Apply operation %s aborting: error_type=%s", op_id, type(exc).__name__
        )
        recovery_complete = True
        try:
            await self.publication.revoke(op_id, generation, candidate_hash)
            await self._maybe_await(
                self.supervisor_client.restore_network_snapshot(
                    operation_id=op_id,
                    execution_generation=generation,
                    old_version=old_applied.version,
                    bind_host=old_applied.bind_host,
                    https_port=old_applied.config.https_port,
                    caddyfile_sha256=old_applied.caddyfile_sha256,
                    caddyfile_path=str(self.export_dir / CADDYFILE_FILENAME),
                )
            )
            if callable(self.on_origins_updated):
                self.on_origins_updated(list(old_applied.origin_whitelist))
        except Exception as comp_exc:
            recovery_complete = False
            logger.warning(
                "Apply operation %s compensation incomplete: error_type=%s",
                op_id,
                type(comp_exc).__name__,
            )
        await self.repo.abort_network_transaction(
            operation_id=op_id,
            execution_generation=generation,
            reason=f"{type(exc).__name__}: {exc}",
            recovery_complete=recovery_complete,
        )

    async def recover_pending_operation(self) -> str:
        txn = await self.repo.get_current_network_transaction()
        if txn is None:
            return "none"
        if txn.decision == "commit":
            await self._finalize_commit(txn)
            return "commit"
        if txn.decision == "abort":
            if not txn.recovery_complete:
                complete = await self._restore_old(txn)
                if complete:
                    await self.repo.abort_network_transaction(
                        operation_id=txn.operation_id,
                        execution_generation=txn.execution_generation,
                        reason="recovery",
                        recovery_complete=True,
                    )
            return "abort"
        await self.repo.abort_network_transaction(
            operation_id=txn.operation_id,
            execution_generation=txn.execution_generation,
            reason="recovery without finality",
            recovery_complete=False,
        )
        complete = await self._restore_old(txn)
        if complete:
            await self.repo.abort_network_transaction(
                operation_id=txn.operation_id,
                execution_generation=txn.execution_generation,
                reason="recovery",
                recovery_complete=True,
            )
        return "no_finality_abort"

    async def wait_for_operation(
        self, operation_id: str, timeout: float = 10.0
    ) -> NetworkApplyOperation:
        """Wait for operation to reach a terminal phase."""
        task = self._background_tasks.get(operation_id)
        if task:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
            except (TimeoutError, Exception):
                pass
        op = await self.repo.get_network_operation(operation_id)
        if not op:
            raise ValueError(f"Operation {operation_id} not found")
        return op

    def check_entry_disconnect(
        self,
        current_host: str,
        target_config: NetworkAccessConfig,
    ) -> tuple[bool, str]:
        """Check if switching to target_config will make current_host unreachable (AC-009)."""
        host_clean = current_host.split(":")[0].strip()
        is_loopback = host_clean in ("127.0.0.1", "localhost")
        port = target_config.https_port

        # Switching to loopback only when current client is on LAN IP
        if not target_config.lan_access_enabled and not is_loopback:
            return True, f"https://127.0.0.1:{port}"

        # Switching LAN IP when current client is on old LAN IP
        if (
            target_config.lan_access_enabled
            and not is_loopback
            and target_config.lan_advertised_ip
            and host_clean != target_config.lan_advertised_ip
        ):
            return True, f"https://{target_config.lan_advertised_ip}:{port}"

        suggested = (
            f"https://{target_config.lan_advertised_ip}:{port}"
            if target_config.lan_access_enabled and target_config.lan_advertised_ip
            else f"https://127.0.0.1:{port}"
        )
        return False, suggested
