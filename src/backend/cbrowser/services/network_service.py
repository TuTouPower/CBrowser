"""Service layer for Network Access settings and Apply Operation state machine."""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.domain.models import (
    AppliedNetworkAccessVersion,
    NetworkAccessConfig,
    NetworkAccessSettingsResponse,
    NetworkApplyOperation,
    NetworkApplyPhase,
    utc_now_iso,
)
from cbrowser.network_config import (
    compute_caddyfile_sha256,
    derive_origin_whitelist,
    generate_caddyfile,
    write_applied_network_state,
)

logger = logging.getLogger("cbrowser.network_service")


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
    ) -> None:
        self.repo = repo
        self.auth_service = auth_service
        self.supervisor_client = supervisor_client
        self.export_dir = export_dir
        self.api_upstream = api_upstream
        self.gateway_upstream = gateway_upstream
        self.on_origins_updated = on_origins_updated
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
        # 1. Verify admin password
        is_valid = await self.auth_service.verify_admin_password(admin_password)
        if not is_valid:
            raise PermissionError("Invalid admin password")

        # 2. Check concurrency
        active_op = await self.repo.get_active_network_operation()
        if active_op and active_op.phase not in (
            NetworkApplyPhase.COMPLETED,
            NetworkApplyPhase.FAILED,
        ):
            raise RuntimeError("Apply operation already in progress")

        # 3. Create target version and operation
        current_settings = await self.repo.get_network_access_settings()
        target_version_num = current_settings.applied_version.version + 1
        target_config = current_settings.pending_config
        target_port = target_config.https_port
        bind_host = "0.0.0.0" if target_config.lan_access_enabled else "127.0.0.1"

        # Generate Caddyfile and metadata
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
        origin_whitelist = derive_origin_whitelist(dummy_ver)

        new_version = AppliedNetworkAccessVersion(
            version=target_version_num,
            config=target_config,
            bind_host=bind_host,
            applied_at=utc_now_iso(),
            caddyfile_sha256=caddy_sha,
            origin_whitelist=origin_whitelist,
        )

        op_id = str(uuid.uuid4())
        new_entry_url = None
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
        await self.repo.save_network_operation(op)

        # 4. Launch asynchronous execution
        task = asyncio.create_task(
            self._execute_apply(op, new_version, caddy_content)
        )
        self._background_tasks[op_id] = task
        return op

    async def _execute_apply(
        self,
        op: NetworkApplyOperation,
        new_version: AppliedNetworkAccessVersion,
        caddyfile_content: str,
    ) -> None:
        self.export_dir.mkdir(parents=True, exist_ok=True)
        staging_caddy = self.export_dir / f"Caddyfile.staging.{op.operation_id}"
        try:
            # Write staging caddyfile for supervisor verification
            staging_caddy.write_text(caddyfile_content, encoding="utf-8")
            staging_caddy.chmod(0o644)

            # Phase 1: Rebuilding Caddy
            op.phase = NetworkApplyPhase.REBUILDING_CADDY
            op.updated_at = utc_now_iso()
            await self.repo.save_network_operation(op)

            # Call supervisor to rebuild edge proxy with staging caddyfile
            await self.supervisor_client.rebuild_edge(
                target_version=new_version.version,
                bind_host=new_version.bind_host,
                https_port=new_version.config.https_port,
                caddyfile_path=str(staging_caddy),
            )

            # Phase 2: Rebuilding Stream (converging running sessions)
            op.phase = NetworkApplyPhase.REBUILDING_STREAM
            op.updated_at = utc_now_iso()
            await self.repo.save_network_operation(op)

            advertised_ip = new_version.config.lan_advertised_ip if new_version.config.lan_access_enabled else "127.0.0.1"
            await self.supervisor_client.converge_network_streams(
                target_version=new_version.version,
                bind_host=new_version.bind_host,
                advertised_ip=advertised_ip,
            )

            # Phase 3: Verifying Readiness
            op.phase = NetworkApplyPhase.VERIFYING_READINESS
            op.updated_at = utc_now_iso()
            await self.repo.save_network_operation(op)

            # Phase 4: Completed - atomically commit to disk and database
            write_applied_network_state(
                self.export_dir,
                new_version,
                caddyfile_content,
            )
            staging_caddy.unlink(missing_ok=True)
            await self.repo.record_applied_network_version(new_version)
            op.phase = NetworkApplyPhase.COMPLETED
            op.updated_at = utc_now_iso()
            await self.repo.save_network_operation(op)
            if callable(self.on_origins_updated):
                try:
                    self.on_origins_updated(new_version.origin_whitelist)
                except Exception as exc:
                    logger.warning("on_origins_updated callback failed: %s", exc)
            logger.info("Apply operation %s completed successfully to version %d", op.operation_id, new_version.version)

        except Exception as e:
            staging_caddy.unlink(missing_ok=True)
            logger.exception("Apply operation %s failed: %s", op.operation_id, e)
            op.phase = NetworkApplyPhase.FAILED
            op.error_reason = f"{type(e).__name__}: {e}"
            op.updated_at = utc_now_iso()
            await self.repo.save_network_operation(op)

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
