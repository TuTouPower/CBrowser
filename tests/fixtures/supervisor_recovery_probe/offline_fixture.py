"""Offline Recovery E2E Probe and Fixtures.

Encapsulates:
- RealApiProcess: Manages independent uvicorn Control API process with
  SQLite WAL database.
- RealSupervisorProcess: Manages independent Supervisor process runner.
- OfflineGatewayMock: Local aiohttp WebSocket Gateway verifying
  AgentCredentials and GatewayControl.
- RealBrowserActionProbe: Triggers in-container clean browser exit via
  UDS /run/cbrowser/runtime/agent.sock.
- SpoolDirectoryWatcher: Watches data_root/spool for atomic event
  persistence and subsequent consumption.
- SandboxContainerTracker: Exact, bounded cleanup of owned Docker containers.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

import docker
import docker.errors
import httpx
import pytest

_gw_fixture_path = Path(__file__).resolve().parent / "gateway_fixture.py"
_gw_spec = importlib.util.spec_from_file_location("gateway_fixture", _gw_fixture_path)
_gw_mod = importlib.util.module_from_spec(_gw_spec)

_auth_path = Path(__file__).resolve().parents[1] / "api_auth.py"
_auth_spec = importlib.util.spec_from_file_location("api_auth", _auth_path)
_auth_mod = importlib.util.module_from_spec(_auth_spec)
sys.modules["api_auth"] = _auth_mod
_auth_spec.loader.exec_module(_auth_mod)
create_auth_context = _auth_mod.create_auth_context
sys.modules["gateway_fixture"] = _gw_mod
_gw_spec.loader.exec_module(_gw_mod)
SupervisorGatewayFixture = _gw_mod.SupervisorGatewayFixture

logger = logging.getLogger("cbrowser.tests.offline_recovery_probe")


def get_e2e_prerequisites() -> tuple[str, str, Path, Path]:
    """Retrieve and validate mandatory E2E images and cache paths from environment.

    Skips the test if variables are missing. Fails if variables are present but
    invalid.
    """
    missing = []
    browser_img = os.environ.get("CBROWSER_RUNTIME_TEST_IMAGE")
    stream_img = os.environ.get("CBROWSER_STREAM_TEST_IMAGE")
    engine_cache = os.environ.get("CBROWSER_RUNTIME_ENGINE_CACHE")
    geoip_cache = os.environ.get("CBROWSER_RUNTIME_GEOIP_CACHE")

    if not browser_img:
        missing.append("CBROWSER_RUNTIME_TEST_IMAGE")
    if not stream_img:
        missing.append("CBROWSER_STREAM_TEST_IMAGE")
    if not engine_cache:
        missing.append("CBROWSER_RUNTIME_ENGINE_CACHE")
    if not geoip_cache:
        missing.append("CBROWSER_RUNTIME_GEOIP_CACHE")

    if missing:
        pytest.skip(f"Missing required E2E environment variables: {', '.join(missing)}")

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
                except Exception as e:
                    logger.error(f"Error cleaning container {name_or_id}: {e}")
                    errors.append(e)

            for net_name_or_id in reversed(self.owned_networks):
                try:
                    net = d_client.networks.get(net_name_or_id)
                    net.remove()
                    logger.info(f"Cleaned up owned sandbox network: {net_name_or_id}")
                except docker.errors.NotFound:
                    pass
                except Exception as e:
                    logger.error(f"Error cleaning network {net_name_or_id}: {e}")
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
        self.auth_context = create_auth_context(
            log_path.parent, origin=f"http://127.0.0.1:{port}"
        )
        self.auth_headers: dict[str, str] = {}
        self.proc: Optional[subprocess.Popen] = None
        self._log_file_handle: Optional[Any] = None

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
            **self.auth_context.env,
        )
        self._log_file_handle = open(self.log_path, "a", encoding="utf-8")
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

        raise TimeoutError(f"API process did not become healthy within {timeout_sec}s")

    def stop(self, timeout_sec: float = 5.0) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        logger.info(f"Real API process stopped (PID {self.proc.pid})")
        self.proc = None
        if self._log_file_handle:
            try:
                self._log_file_handle.close()
            except Exception:
                pass
            self._log_file_handle = None

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


class RealSupervisorProcess:
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
        coturn_container_id: Optional[str] = None,
    ) -> None:
        self.api_url = api_url
        self.data_root = data_root
        self.engine_cache = engine_cache
        self.geoip_cache = geoip_cache
        self.token_file = token_file
        self.agent_key_file = agent_key_file
        self.gateway_url = gateway_url
        self.gateway_control_url = gateway_control_url
        self.gateway_token_file = gateway_token_file
        self.prefix = prefix
        self.port = port
        self.root = root
        self.env = env
        self.log_path = log_path
        self.coturn_container_id = coturn_container_id
        self.proc: Optional[subprocess.Popen] = None
        self._log_file_handle: Optional[Any] = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _auth_headers(self) -> dict[str, str]:
        if self.token_file and self.token_file.is_file():
            t = self.token_file.read_text(encoding="utf-8").strip()
            return {"Authorization": f"Bearer {t}"}
        return {}

    def start(self, timeout_sec: float = 20.0) -> None:
        if self.proc is not None and self.proc.poll() is None:
            raise RuntimeError(
                f"Supervisor process already running (PID {self.proc.pid})"
            )

        cmd = [
            sys.executable,
            "-m",
            "cbrowser.supervisor.runner",
            "--api-url",
            self.api_url,
            "--data-root",
            str(self.data_root),
            "--engine-cache",
            str(self.engine_cache),
            "--geoip-cache",
            str(self.geoip_cache),
            "--token-file",
            str(self.token_file),
            "--agent-key-file",
            str(self.agent_key_file),
            "--gateway-url",
            self.gateway_url,
            "--gateway-control-url",
            self.gateway_control_url,
            "--gateway-token-file",
            str(self.gateway_token_file),
            "--prefix",
            self.prefix,
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
        ]
        if self.coturn_container_id:
            cmd.extend(["--coturn-container-id", self.coturn_container_id])
        sup_env = dict(self.env)
        sup_env.update(
            PYTHONPATH=str(self.root / "src/backend"),
            PYTHONDONTWRITEBYTECODE="1",
        )
        self._log_file_handle = open(self.log_path, "a", encoding="utf-8")
        self.proc = subprocess.Popen(
            cmd,
            cwd=self.root,
            env=sup_env,
            stdout=self._log_file_handle,
            stderr=subprocess.STDOUT,
        )

        headers = self._auth_headers()
        deadline = time.monotonic() + timeout_sec
        with httpx.Client(
            base_url=self.url, headers=headers, trust_env=False
        ) as client:
            while time.monotonic() < deadline:
                if self.proc.poll() is not None:
                    raise RuntimeError(
                        "Supervisor process exited prematurely with exit code "
                        f"{self.proc.returncode}"
                    )
                try:
                    resp = client.get("/supervisor/v1/health", timeout=1.0)
                    if resp.status_code == 200:
                        logger.info(
                            f"Real Supervisor process online on port {self.port} "
                            f"(PID {self.proc.pid})"
                        )
                        return
                except httpx.TransportError:
                    pass
                time.sleep(0.1)

        raise TimeoutError(
            f"Supervisor process did not become healthy within {timeout_sec}s"
        )

    def sigkill(self) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            pid = self.proc.pid
            self.proc.send_signal(signal.SIGKILL)
            self.proc.wait()
            logger.info(f"Supervisor process SIGKILL executed on PID {pid}")
        self.proc = None
        if self._log_file_handle:
            try:
                self._log_file_handle.close()
            except Exception:
                pass
            self._log_file_handle = None

    def stop(self, timeout_sec: float = 5.0) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        logger.info(f"Supervisor process stopped (PID {self.proc.pid})")
        self.proc = None
        if self._log_file_handle:
            try:
                self._log_file_handle.close()
            except Exception:
                pass
            self._log_file_handle = None

    def restart(self, timeout_sec: float = 20.0) -> None:
        self.stop()
        self.start(timeout_sec=timeout_sec)


OfflineGatewayMock = SupervisorGatewayFixture


class RealBrowserActionProbe:
    @staticmethod
    def trigger_clean_close(browser_container_name: str) -> str:
        script = (
            "import httpx; "
            "transport = httpx.HTTPTransport(uds='/run/cbrowser/runtime/agent.sock'); "
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
