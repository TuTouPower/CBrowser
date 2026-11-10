"""Offline Recovery E2E Probe and Fixtures.

Encapsulates:
- RealApiProcess: Manages independent uvicorn Control API process with
  SQLite WAL database.
- RealSupervisorProcess: Manages independent Supervisor process runner.
- RealBrowserActionProbe: Triggers in-container clean browser exit via
  UDS (container_agent_socket_path(), root /run/cb/socks).
- SpoolDirectoryWatcher: Watches data_root/spool for atomic event
  persistence and subsequent consumption.
- SandboxContainerTracker: Exact, bounded cleanup of owned Docker containers.

The Gateway counterparty is the production application in
``supervisor_recovery_probe.gateway_service``; this module no longer ships a
Gateway double.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import docker
import docker.errors
import httpx

from e2e_env import require_e2e_env
from api_auth import create_auth_context
from cbrowser.gateway.endpoint import DEFAULT_GATEWAY_PORT, GatewayEndpoint
from cbrowser.runtime_agent.socket_root import (
    AGENT_SOCKET_ROOT_ENV,
    DEFAULT_AGENT_SOCKET_ROOT,
)

logger = logging.getLogger("cbrowser.tests.offline_recovery_probe")


def get_e2e_prerequisites() -> tuple[str, str, Path, Path]:
    """Retrieve and validate mandatory E2E images and cache paths from environment.

    Skips the test if variables are missing. Fails if variables are present but
    invalid.
    """
    env = require_e2e_env(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_STREAM_TEST_IMAGE",
        "CBROWSER_RUNTIME_ENGINE_CACHE",
        "CBROWSER_RUNTIME_GEOIP_CACHE",
    )
    browser_img = env["CBROWSER_RUNTIME_TEST_IMAGE"]
    stream_img = env["CBROWSER_STREAM_TEST_IMAGE"]
    engine_cache = env["CBROWSER_RUNTIME_ENGINE_CACHE"]
    geoip_cache = env["CBROWSER_RUNTIME_GEOIP_CACHE"]

    assert browser_img.startswith("sha256:"), (
        "CBROWSER_RUNTIME_TEST_IMAGE must be sha256 immutable digest, "
        f"got {browser_img}"
    )
    assert stream_img.startswith("sha256:"), (
        f"CBROWSER_STREAM_TEST_IMAGE must be sha256 immutable digest, got {stream_img}"
    )
    engine_path = Path(engine_cache)
    geoip_path = Path(geoip_cache)
    assert engine_path.is_dir(), (
        f"CBROWSER_RUNTIME_ENGINE_CACHE is not a valid directory: {engine_cache}"
    )
    assert geoip_path.is_dir(), (
        f"CBROWSER_RUNTIME_GEOIP_CACHE is not a valid directory: {geoip_cache}"
    )
    d_client = docker.from_env()
    try:
        d_client.images.get(browser_img)
        d_client.images.get(stream_img)
    finally:
        d_client.close()
    return browser_img, stream_img, engine_path, geoip_path


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def prepare_engine_cache(
    data_root: Path,
    engine_src: Path | None = None,
    geoip_src: Path | None = None,
) -> tuple[Path, Path]:
    if engine_src is None or geoip_src is None:
        _, _, env_engine, env_geoip = get_e2e_prerequisites()
        if engine_src is None:
            engine_src = env_engine
        if geoip_src is None:
            geoip_src = env_geoip
    assert engine_src.is_dir(), f"Engine cache directory does not exist: {engine_src}"
    assert geoip_src.is_dir(), f"GeoIP cache directory does not exist: {geoip_src}"
    engine_cache_dest = data_root / "engine_cache"
    geoip_cache_dest = engine_cache_dest / "geoip"
    shutil.copytree(engine_src, engine_cache_dest, dirs_exist_ok=True)
    shutil.copytree(geoip_src, geoip_cache_dest, dirs_exist_ok=True)
    return engine_cache_dest, geoip_cache_dest


class SandboxContainerTracker:
    def __init__(self) -> None:
        self.owned_containers: list[str] = []
        self.owned_networks: list[str] = []

    def track(self, name_or_id: str) -> None:
        if name_or_id and name_or_id not in self.owned_containers:
            self.owned_containers.append(name_or_id)

    def track_network(self, name_or_id: str) -> None:
        if name_or_id and name_or_id not in self.owned_networks:
            self.owned_networks.append(name_or_id)

    def cleanup(self) -> None:
        d_client = None
        errors: list[Exception] = []
        try:
            d_client = docker.from_env()
            for name_or_id in reversed(self.owned_containers):
                try:
                    c = d_client.containers.get(name_or_id)
                    c.remove(force=True)
                    logger.info(f"Cleaned up owned sandbox container: {name_or_id}")
                except docker.errors.NotFound:
                    pass
                except Exception as e:  # noqa: BLE001 - robust sandbox container cleanup
                    logger.error(
                        "Error cleaning container %s: %s",
                        name_or_id,
                        type(e).__name__,
                    )
                    errors.append(e)

            for net_name_or_id in reversed(self.owned_networks):
                try:
                    net = d_client.networks.get(net_name_or_id)
                    net.remove()
                    logger.info(f"Cleaned up owned sandbox network: {net_name_or_id}")
                except docker.errors.NotFound:
                    pass
                except Exception as e:  # noqa: BLE001 - robust sandbox network cleanup
                    logger.error(
                        "Error cleaning network %s: %s",
                        net_name_or_id,
                        type(e).__name__,
                    )
                    errors.append(e)
        finally:
            if d_client:
                d_client.close()
        if errors:
            raise RuntimeError(f"Cleanup encountered errors: {errors}")


class RealApiProcess:
    def __init__(
        self,
        port: int,
        db_path: Path,
        token_file: Path,
        root: Path,
        env: dict[str, str],
        log_path: Path,
    ) -> None:
        self.port = port
        self.db_path = db_path
        self.token_file = token_file
        self.root = root
        self.env = env
        self.log_path = log_path
        self.auth_context = create_auth_context(log_path.parent)
        self.auth_headers: dict[str, str] = {}
        self.proc: subprocess.Popen | None = None
        self._log_file_handle: Any | None = None

    @property
    def log_handle_closed(self) -> bool:
        """Whether the spawned process log handle is closed."""
        return self._log_file_handle is None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, timeout_sec: float = 20.0) -> None:
        if self.proc is not None and self.proc.poll() is None:
            raise RuntimeError(f"API process already running (PID {self.proc.pid})")

        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "cbrowser.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--log-level",
            "info",
        ]
        api_env = dict(self.env)
        api_env.update(
            CBROWSER_DB_PATH=str(self.db_path),
            CBROWSER_SUPERVISOR_TOKEN_FILE=str(self.token_file),
            PYTHONPATH=str(self.root / "src/backend"),
            PYTHONDONTWRITEBYTECODE="1",
            **{
                key: value
                for key, value in self.auth_context.env.items()
                if key != "CBROWSER_SUPERVISOR_TOKEN_FILE"
            },
        )
        self._log_file_handle = open(  # noqa: SIM115 - managed log handle closed in stop()
            self.log_path, "a", encoding="utf-8"
        )
        try:
            self.proc = subprocess.Popen(
                cmd,
                cwd=self.root,
                env=api_env,
                stdout=self._log_file_handle,
                stderr=subprocess.STDOUT,
            )

            deadline = time.monotonic() + timeout_sec
            with httpx.Client(base_url=self.url, trust_env=False) as client:
                while time.monotonic() < deadline:
                    if self.proc.poll() is not None:
                        raise RuntimeError(
                            "API process exited prematurely with exit code "
                            f"{self.proc.returncode}"
                        )
                    try:
                        resp = client.get("/api/v1/health", timeout=1.0)
                        if resp.status_code == 200:
                            self.auth_headers = self.auth_context.login_sync(self.url)
                            logger.info(
                                f"Real API process online on port {self.port} "
                                f"(PID {self.proc.pid})"
                            )
                            return
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)

            raise TimeoutError(
                f"API process did not become healthy within {timeout_sec}s"
            )
        except BaseException as exc:
            logger.error(
                "RealApiProcess start failed: %s; cleaning up child process",
                type(exc).__name__,
            )
            try:
                self.stop()
            except BaseException as stop_exc:
                logger.error(
                    "RealApiProcess cleanup also failed: %s",
                    type(stop_exc).__name__,
                )
                raise stop_exc from exc
            raise

    def stop(self, timeout_sec: float = 5.0) -> None:
        if self.proc is None and self._log_file_handle is None:
            return
        try:
            if self.proc is not None and self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=timeout_sec)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=2.0)
            if self.proc is not None and self.proc.poll() is not None:
                logger.info("Real API process stopped (PID %s)", self.proc.pid)
                self.proc = None
        finally:
            handle = self._log_file_handle
            self._log_file_handle = None
            if handle is not None:
                handle.close()

    def verify_offline(self, timeout_sec: float = 3.0) -> bool:
        try:
            with httpx.Client(
                base_url=self.url, timeout=timeout_sec, trust_env=False
            ) as client:
                client.get("/api/v1/health")
                return False
        except httpx.TransportError:
            return True

    def restart(self, timeout_sec: float = 20.0) -> None:
        self.stop()
        self.start(timeout_sec=timeout_sec)


class RealSupervisorContainer:
    def __init__(
        self,
        api_url: str,
        data_root: Path,
        engine_cache: Path,
        geoip_cache: Path,
        token_file: Path,
        agent_key_file: Path,
        gateway_url: str,
        gateway_control_url: str,
        gateway_token_file: Path,
        prefix: str,
        port: int,
        root: Path,
        env: dict[str, str],
        log_path: Path,
        gateway_port: int | None = None,
        docker_client: docker.DockerClient | None = None,
        supervisor_image: str | None = None,
        network: str | None = None,
        udp_mux_min_port: int = 30000,
        udp_mux_max_port: int = 30991,
    ) -> None:
        self.api_url = api_url
        self.data_root = data_root.resolve()
        self.engine_cache = engine_cache.resolve()
        self.geoip_cache = geoip_cache.resolve()
        self.token_file = token_file.resolve()
        self.agent_key_file = agent_key_file.resolve()
        self.gateway_url = gateway_url
        self.gateway_control_url = gateway_control_url
        self.gateway_token_file = gateway_token_file.resolve()
        self.prefix = prefix
        self.port = port
        self.root = root
        self.env = env
        self.log_path = log_path
        if gateway_port is not None:
            self.gateway_port = gateway_port
        elif self.gateway_url:
            try:
                self.gateway_port = GatewayEndpoint.from_url(self.gateway_url).port
            except ValueError:
                self.gateway_port = DEFAULT_GATEWAY_PORT
        else:
            self.gateway_port = DEFAULT_GATEWAY_PORT

        self.docker_client = docker_client or docker.from_env()
        self.supervisor_image = supervisor_image or require_e2e_env(
            "CBROWSER_SUPERVISOR_TEST_IMAGE"
        )["CBROWSER_SUPERVISOR_TEST_IMAGE"]
        self.network = network
        self.udp_mux_min_port = udp_mux_min_port
        self.udp_mux_max_port = udp_mux_max_port
        self.container: docker.models.containers.Container | None = None
        self.last_container_id: str | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def container_id(self) -> str | None:
        if self.container is not None:
            return self.container.id
        return self.last_container_id

    def _auth_headers(self) -> dict[str, str]:
        if self.token_file and self.token_file.is_file():
            t = self.token_file.read_text(encoding="utf-8").strip()
            return {"Authorization": f"Bearer {t}"}
        return {}

    def _prepare_secrets(self) -> tuple[Path, Path, Path]:
        control_dir = self.data_root / "control"
        control_dir.mkdir(parents=True, exist_ok=True)
        control_dir.chmod(0o700)

        def _sync_secret(src_path: Path, filename: str) -> Path:
            dst_path = control_dir / filename
            if src_path != dst_path:
                content = src_path.read_text(encoding="utf-8")
                dst_path.write_text(content, encoding="utf-8")
            dst_path.chmod(0o600)
            return dst_path

        sup_token_dst = _sync_secret(self.token_file, self.token_file.name)
        agent_key_dst = _sync_secret(self.agent_key_file, self.agent_key_file.name)
        gw_token_dst = _sync_secret(
            self.gateway_token_file, self.gateway_token_file.name
        )
        return sup_token_dst, agent_key_dst, gw_token_dst

    def _build_mounts(self) -> dict[str, dict[str, str]]:
        mounts: dict[str, dict[str, str]] = {
            str(self.data_root / name): {
                "bind": str(self.data_root / name),
                "mode": "rw",
            }
            for name in (
                "profiles",
                "runtime",
                "runtime-events",
                "artifacts",
                "spool",
                "control",
            )
        }
        mounts[str(self.engine_cache)] = {
            "bind": str(self.engine_cache),
            "mode": "rw",
        }
        mounts[str(self.geoip_cache)] = {
            "bind": str(self.geoip_cache),
            "mode": "rw",
        }
        mounts["/var/run/docker.sock"] = {
            "bind": "/var/run/docker.sock",
            "mode": "ro",
        }
        mounts[DEFAULT_AGENT_SOCKET_ROOT] = {
            "bind": DEFAULT_AGENT_SOCKET_ROOT,
            "mode": "rw",
        }
        return mounts

    def _build_command(
        self,
        token_path: Path,
        agent_path: Path,
        gw_token_path: Path,
    ) -> list[str]:
        cmd = [
            "--api-url",
            self.api_url,
            "--data-root",
            str(self.data_root),
            "--engine-cache",
            str(self.engine_cache),
            "--geoip-cache",
            str(self.geoip_cache),
            "--token-file",
            str(token_path),
            "--agent-key-file",
            str(agent_path),
            "--gateway-url",
            self.gateway_url,
            "--gateway-port",
            str(self.gateway_port),
            "--gateway-control-url",
            self.gateway_control_url,
            "--gateway-token-file",
            str(gw_token_path),
            "--prefix",
            self.prefix,
            "--host",
            "0.0.0.0",
            "--port",
            "8005",
        ]
        return cmd

    def start(self, timeout_sec: float = 30.0) -> None:
        if self.container is not None:
            raise RuntimeError("Supervisor container already running")

        assert self.supervisor_image.startswith("sha256:"), (
            f"Invalid supervisor image: {self.supervisor_image}"
        )

        for name in (
            "profiles", "runtime", "runtime-events", "artifacts", "spool", "control"
        ):
            (self.data_root / name).mkdir(parents=True, exist_ok=True)

        sup_token_p, agent_p, gw_token_p = self._prepare_secrets()
        mounts = self._build_mounts()
        cmd = self._build_command(sup_token_p, agent_p, gw_token_p)

        container_env = {
            "CBROWSER_BROWSER_IMAGE": os.environ.get(
                "CBROWSER_RUNTIME_TEST_IMAGE", ""
            ),
            "CBROWSER_STREAM_IMAGE": os.environ.get("CBROWSER_STREAM_TEST_IMAGE", ""),
            "CBROWSER_NETWORK_POLICY_IMAGE": self.supervisor_image,
            "CBROWSER_UDP_MUX_MIN_PORT": str(self.udp_mux_min_port),
            "CBROWSER_UDP_MUX_MAX_PORT": str(self.udp_mux_max_port),
            "CBROWSER_MEDIA_SUBNET_POOL": os.environ.get(
                "CBROWSER_E2E_MEDIA_POOL", "10.251.0.0/16"
            ),
            AGENT_SOCKET_ROOT_ENV: DEFAULT_AGENT_SOCKET_ROOT,
        }

        c_name = f"{self.prefix}-supervisor-{uuid.uuid4().hex[:6]}"
        run_kwargs: dict[str, Any] = {
            "name": c_name,
            "detach": True,
            "read_only": True,
            "cap_drop": ["ALL"],
            "cap_add": ["FOWNER", "DAC_OVERRIDE", "CHOWN"],
            "security_opt": ["no-new-privileges:true"],
            "tmpfs": {"/tmp": "rw,size=256m"},
            "environment": container_env,
            "volumes": mounts,
            "ports": {"8005/tcp": ("127.0.0.1", self.port)},
            "command": cmd,
            "labels": {
                "com.cbrowser.prefix": self.prefix,
                "com.cbrowser.managed-by": "supervisor",
                "com.cbrowser.role": "supervisor",
            },
        }
        if self.network:
            run_kwargs["network"] = self.network

        try:
            self.container = self.docker_client.containers.run(
                self.supervisor_image, **run_kwargs
            )
            self.last_container_id = self.container.id

            headers = self._auth_headers()
            deadline = time.monotonic() + timeout_sec
            with httpx.Client(
                base_url=self.url, headers=headers, trust_env=False
            ) as client:
                while time.monotonic() < deadline:
                    self.container.reload()
                    if self.container.status not in ("running", "created"):
                        st = self.container.status
                        raise RuntimeError(f"Supervisor container exited ({st})")
                    try:
                        resp = client.get("/supervisor/v1/health", timeout=1.0)
                        if resp.status_code == 200:
                            logger.info(
                                "Supervisor container online port %d (%s)",
                                self.port,
                                self.container.id[:12],
                            )
                            return
                    except httpx.TransportError:
                        pass
                    time.sleep(0.2)

            raise TimeoutError(
                f"Supervisor container did not become healthy within {timeout_sec}s"
            )
        except BaseException as start_exc:
            err_type = type(start_exc).__name__
            logger.error("Supervisor container start failed: %s", err_type)
            try:
                self.stop()
            except BaseException as stop_exc:
                raise stop_exc from start_exc
            raise

    def sigkill(self, timeout_sec: float = 10.0) -> None:
        if self.container is None:
            return
        c = self.container
        self.last_container_id = c.id
        c.kill(signal="SIGKILL")

        deadline = time.monotonic() + timeout_sec
        exit_code = None
        oom_killed = None
        reload_errors = []
        while time.monotonic() < deadline:
            try:
                c.reload()
                st = getattr(c, "attrs", {}).get("State", {}) or {}
                if st.get("Status") in ("exited", "dead"):
                    exit_code = st.get("ExitCode")
                    oom_killed = st.get("OOMKilled")
                    break
            except docker.errors.NotFound:
                break
            except Exception as exc:  # noqa: BLE001 - robust docker reload during sigkill wait
                reload_errors.append(type(exc).__name__)
            time.sleep(0.1)

        if exit_code is None:
            err_msg = (
                f"Timed out waiting for SIGKILL exit (reloads={len(reload_errors)})"
            )
            logger.error("Supervisor container sigkill timeout on %s", c.id[:12])
            raise TimeoutError(err_msg)

        assert exit_code == 137, f"Expected ExitCode 137 on SIGKILL, got {exit_code}"
        assert oom_killed is False, "Container must not be OOM killed"

        self._save_logs(c)
        try:
            c.remove(force=True, v=True)
            self.container = None
        except docker.errors.NotFound:
            self.container = None
        except Exception as exc:
            err_type = type(exc).__name__
            logger.error(
                "Error removing killed container %s: %s",
                c.id[:12],
                err_type,
            )
            raise RuntimeError(
                f"Supervisor container remove failed on sigkill: {err_type}"
            ) from exc

        logger.info("Supervisor container SIGKILL on %s (code 137)", c.id[:12])

    def _save_logs(self, c: Any) -> None:
        if not self.log_path:
            return
        try:
            logs = c.logs()
            if isinstance(logs, str):
                data = logs.encode("utf-8")
            elif isinstance(logs, (bytes, bytearray)):
                data = bytes(logs)
            else:
                data = b""
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "ab") as f:
                f.write(data)
        except docker.errors.NotFound:
            pass
        except Exception as exc:
            logger.error(
                "Failed to save container logs to %s: %s",
                self.log_path,
                type(exc).__name__,
            )
            raise

    def stop(self, timeout_sec: float = 5.0) -> None:
        if self.container is None:
            return
        c = self.container
        self.last_container_id = c.id
        stop_err = None
        try:
            c.stop(timeout=int(timeout_sec))
        except docker.errors.NotFound:
            pass
        except Exception as exc:  # noqa: BLE001 - robust container stop error recording
            stop_err = exc
            logger.warning(
                "Error stopping supervisor container: %s", type(exc).__name__
            )

        try:
            self._save_logs(c)
        except Exception as exc:  # noqa: BLE001 - robust log save error recording
            if stop_err is None:
                stop_err = exc

        remove_err = None
        try:
            c.remove(force=True, v=True)
            self.container = None
        except docker.errors.NotFound:
            self.container = None
        except Exception as exc:  # noqa: BLE001 - robust container remove error recording
            remove_err = exc
            logger.error(
                "Error removing supervisor container: %s", type(exc).__name__
            )

        err = remove_err or stop_err
        if err is not None:
            raise RuntimeError(
                f"Supervisor container stop/remove failed: {type(err).__name__}"
            ) from err

    def restart(self, timeout_sec: float = 30.0) -> None:
        self.stop()
        self.start(timeout_sec=timeout_sec)


class RealBrowserActionProbe:
    @staticmethod
    def trigger_clean_close(browser_container_name: str) -> str:
        script = (
            "import httpx; "
            "from cbrowser.runtime_agent.socket_root import container_agent_socket_path; "
            "transport = httpx.HTTPTransport(uds=container_agent_socket_path()); "
            "client = httpx.Client(transport=transport, base_url='http://uds'); "
            "r = client.post('/control', json={'action': 'close'}); "
            "assert r.status_code == 200, r.text; "
            "client.close()"
        )
        res = subprocess.run(
            ["docker", "exec", browser_container_name, "python3", "-c", script],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        logger.info(
            f"Triggered clean close on {browser_container_name}: {res.stdout.strip()}"
        )
        return res.stdout


class SpoolDirectoryWatcher:
    def __init__(self, spool_dir: Path) -> None:
        self.spool_dir = Path(spool_dir)

    async def wait_for_spool_event(
        self, expected_profile_id: str, timeout_sec: float = 30.0
    ) -> tuple[Path, dict[str, Any]]:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if self.spool_dir.exists():
                for f in sorted(self.spool_dir.glob("*.json")):
                    try:
                        content = f.read_text(encoding="utf-8")
                        data = json.loads(content)
                        if (
                            data.get("profile_id") == expected_profile_id
                            and data.get("event_type") == "exit"
                        ):
                            return f, data
                    except (json.JSONDecodeError, OSError):
                        pass
            await asyncio.sleep(0.3)
        raise TimeoutError(
            f"Spool exit event for profile {expected_profile_id} "
            f"not found within {timeout_sec}s in {self.spool_dir}"
        )

    async def wait_for_spool_cleared(
        self, spool_file: Path, timeout_sec: float = 30.0
    ) -> None:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if not spool_file.exists():
                return
            await asyncio.sleep(0.3)
        raise TimeoutError(
            f"Spool file {spool_file} was not removed within {timeout_sec}s"
        )
