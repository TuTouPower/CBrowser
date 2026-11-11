"""Docker Real E2E Test Suite verifying all 6 ACs for Browser Runtime.

AC-001: Persistent user data across container recreation & dual profile isolation.
AC-002: Subsystem failure detection, physical X11 geometry 1920x1080 and DPR1.
AC-003: Controlled UDS socket, CDP stream, and RPC allowlist rejection.
AC-004: HTTP download capture and recovery after external automation disconnect.
AC-005: Chrome exit event persistence, lifecycle decoupling & Agent restart.
AC-006: Non-root UID 1000, read-only rootfs, cap-drop ALL, and stream auth.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import os
import tempfile
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

import httpx
import pytest
from wait import poll_until

from e2e_env import require_e2e_env
import uvicorn
from cbrowser.adapters.database.migrations import run_database_migrations
from cbrowser.adapters.database.repository import ProfileRepository
from cbrowser.adapters.database.session import create_engine_and_maker
from cbrowser.api.app import create_app
from cbrowser.domain.models import ConfigVersionSnapshot, ProfileConfig
from cbrowser.runtime_agent.socket_root import (
    AGENT_SOCKET_PATH_ENV,
    AGENT_SOCKET_ROOT_ENV,
    agent_socket_path,
)
from cbrowser.supervisor.artifact_forwarder import DownloadArtifactForwarder


pytestmark = [pytest.mark.serial, pytest.mark.e2e_images('CBROWSER_RUNTIME_TEST_IMAGE')]
logger = logging.getLogger(__name__)

IMAGE_TAG = os.environ.get("CBROWSER_RUNTIME_TEST_IMAGE", "")
ACTIVE_TEST_NETWORK: str | None = None
SCRATCH_ROOT = Path(tempfile.mkdtemp(prefix="cbrowser-t003-e2e-", dir="/tmp"))
ENGINE_CACHE = Path(os.environ.get("CBROWSER_RUNTIME_ENGINE_CACHE", "")).resolve()
LOGS_DIR = Path(tempfile.mkdtemp(prefix="cbrowser-t003-logs-", dir="/tmp"))


@pytest.fixture(scope="session", autouse=True)
def _require_runtime_prerequisites():
    global IMAGE_TAG, ENGINE_CACHE
    env = require_e2e_env(
        "CBROWSER_RUNTIME_TEST_IMAGE",
        "CBROWSER_RUNTIME_ENGINE_CACHE",
        paths=("CBROWSER_RUNTIME_ENGINE_CACHE",),
    )
    IMAGE_TAG = env["CBROWSER_RUNTIME_TEST_IMAGE"]
    ENGINE_CACHE = Path(env["CBROWSER_RUNTIME_ENGINE_CACHE"])
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _free_port() -> int:

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _UvicornThread:
    def __init__(self, app, port: int):
        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> None:
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                return
            time.sleep(0.05)
        raise RuntimeError("uvicorn did not start")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


class MockE2EHttpHandler(BaseHTTPRequestHandler):
    """Local HTTP server serving test pages, cookies, downloads, and audio."""

    def do_GET(self) -> None:
        if self.path.startswith("/set_cookie"):
            cookie_val = self.path.split("val=")[-1]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header(
                "Set-Cookie", f"profile_secret={cookie_val}; Path=/; Max-Age=86400"
            )
            self.end_headers()
            self.wfile.write(b"<html><body>Cookie Set</body></html>")
        elif self.path == "/download-1.txt":
            content = b"E2E_VERIFICATION_CONTENT_FIRST_DOWNLOAD_11111"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header(
                "Content-Disposition", 'attachment; filename="download-1.txt"'
            )
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == "/download-2.txt":
            content = b"E2E_VERIFICATION_CONTENT_SECOND_DOWNLOAD_22222"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header(
                "Content-Disposition", 'attachment; filename="download-2.txt"'
            )
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == "/download-intermediate.txt":
            content = b"E2E_VERIFICATION_CONTENT_INTERMEDIATE_DOWNLOAD_OVERRIDE_ACTIVE"
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header(
                "Content-Disposition",
                'attachment; filename="download-intermediate.txt"',
            )
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == "/file_input.html":
            html = b'<html><body><input id="f" type="file"></body></html>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html)
        elif self.path == "/download_page.html":
            html = (
                b"<html><body>"
                b'<a id="dl1" href="/download-1.txt" download>DL1</a>'
                b'<a id="dl_mid" href="/download-intermediate.txt" download>DL_MID</a>'
                b'<a id="dl2" href="/download-2.txt" download>DL2</a>'
                b"</body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html)
        elif self.path.startswith("/audio_test.html"):
            freq = 440
            if "freq=880" in self.path:
                freq = 880
            html = f"""<!DOCTYPE html><html><head>
<title>WebAudio {freq}Hz Test</title></head>
<body><h1>Audio Running {freq}Hz</h1><script>
window.onload = async () => {{
  const AC = window.AudioContext || window.webkitAudioContext;
  const ctx = new AC();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = 'sine'; osc.frequency.value = {freq};
  osc.frequency.setValueAtTime({freq}, ctx.currentTime);
  gain.gain.value = 0.5;
  gain.gain.setValueAtTime(0.5, ctx.currentTime);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start();
  if (ctx.state !== 'running') {{ await ctx.resume(); }}
  window.__audioCtx = ctx;
}};
</script></body></html>""".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture(scope="session")
def http_server(_require_runtime_prerequisites):
    """Serve synthetic fixtures on a dedicated Docker bridge, without host ports."""
    global ACTIVE_TEST_NETWORK
    run_id = uuid.uuid4().hex[:10]
    network = f"cbrowser-t003-impl-http-{run_id}"
    name = f"cbrowser-t003-impl-http-server-{run_id}"
    script = (
        "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "from typing import Any\nimport json, math, time, urllib.parse\n"
        + inspect.getsource(MockE2EHttpHandler)
        + "\nHTTPServer(('0.0.0.0', 8080), MockE2EHttpHandler).serve_forever()\n"
    )
    subprocess.run(
        ["docker", "network", "create", "--label", "cbrowser.task=t003", network],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "--network",
                network,
                "--label",
                "cbrowser.task=t003",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--entrypoint",
                "python3",
                IMAGE_TAG,
                "-c",
                script,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        ACTIVE_TEST_NETWORK = network
        yield f"http://{name}:8080"
    finally:
        ACTIVE_TEST_NETWORK = None
        subprocess.run(
            ["docker", "rm", "-f", name], capture_output=True, timeout=20, check=False
        )
        subprocess.run(
            ["docker", "network", "rm", network],
            capture_output=True,
            timeout=20,
            check=False,
        )


def create_snapshot_file(
    target_file: Path, profile_id: str, version: int = 1, **config_kwargs: Any
) -> None:
    """Helper to create valid t002 ConfigVersionSnapshot file."""
    config_kwargs.setdefault("geoip", False)
    cfg = ProfileConfig(**config_kwargs)
    snapshot = ConfigVersionSnapshot(
        id=f"snap_{uuid.uuid4().hex[:12]}",
        profile_id=profile_id,
        version=version,
        config=cfg.model_dump(),
        created_at="2026-10-28T00:00:00Z",
    )
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text(
        json.dumps(snapshot.model_dump(), indent=2), encoding="utf-8"
    )


def run_docker_container(
    name: str,
    host_profile_dir: Path,
    host_runtime_dir: Path,
    host_exchange_dir: Path,
    snapshot_path: Path,
    profile_id: str,
    runtime_instance_id: str,
    host_events_dir: Path | None = None,
    host_uploads_dir: Path | None = None,
    display: str = ":99",
) -> str:
    """Run an isolated Browser Runtime container with canonical data layout."""
    if ACTIVE_TEST_NETWORK is None:
        raise RuntimeError("Docker HTTP fixture network is not initialized")
    host_profile_dir.mkdir(parents=True, exist_ok=True)
    host_runtime_dir.mkdir(parents=True, exist_ok=True)
    host_exchange_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir = host_uploads_dir or host_exchange_dir.parent / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    events_dir = (
        host_events_dir or host_runtime_dir.parent / "runtime-events" / profile_id
    )
    events_dir.mkdir(parents=True, exist_ok=True)

    (host_runtime_dir / "x11").mkdir(parents=True, exist_ok=True)
    (host_runtime_dir / "pulse").mkdir(parents=True, exist_ok=True)
    host_socket_root = host_runtime_dir.parent / "sockets"
    host_socket_root.mkdir(parents=True, exist_ok=True)

    # Permission setup for in-container UID 1000
    os.chmod(host_profile_dir, 0o777)
    os.chmod(host_runtime_dir, 0o777)
    os.chmod(host_exchange_dir, 0o777)
    os.chmod(uploads_dir, 0o777)
    os.chmod(events_dir, 0o777)
    os.chmod(host_runtime_dir / "x11", 0o777)
    os.chmod(host_runtime_dir / "pulse", 0o777)
    os.chmod(host_socket_root, 0o777)
    agent_sock = str(
        agent_socket_path(Path("/run/cb/socks"), profile_id, runtime_instance_id)
    )

    # Initialize Linux sticky bit 1777 on X11 directory as required by Xvfb
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            "0:0",
            "--entrypoint",
            "chmod",
            "-v",
            f"{host_runtime_dir / 'x11'}:/x11",
            IMAGE_TAG,
            "1777",
            "/x11",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=15.0,
    )

    target_snap = host_runtime_dir / "snapshot.json"
    if snapshot_path != target_snap:
        shutil.copy2(snapshot_path, target_snap)
    os.chmod(target_snap, 0o644)

    cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        name,
        "--label",
        "cbrowser.task=t003",
        "--label",
        f"com.cbrowser.profile-id={profile_id}",
        "--label",
        f"com.cbrowser.instance-id={runtime_instance_id}",
        "--user",
        "1000:1000",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--ipc",
        "shareable",
        "--shm-size",
        "1g",
        "--network",
        ACTIVE_TEST_NETWORK,
        "--tmpfs",
        "/tmp:rw,exec,nosuid,nodev,size=512m",
        "--tmpfs",
        "/home/cbrowser:rw,mode=0755,size=64m",
        "-v",
        f"{ENGINE_CACHE}:/data/engine-cache:ro",
        "-v",
        f"{host_profile_dir}:/data/profiles/{profile_id}/profile",
        "-v",
        f"{events_dir}:/data/runtime-events/{profile_id}",
        "-v",
        f"{host_exchange_dir}:/exchange/downloads",
        "-v",
        f"{uploads_dir}:/exchange/uploads",
        "-v",
        f"{host_runtime_dir}:/run/cbrowser/runtime",
        "-v",
        f"{host_runtime_dir}/x11:/tmp/.X11-unix",
        "-v",
        f"{host_runtime_dir}/pulse:/pulse",
        "-v",
        f"{host_socket_root}:/run/cb/socks:rw",
        "-e",
        f"{AGENT_SOCKET_ROOT_ENV}=/run/cb/socks",
        "-e",
        f"{AGENT_SOCKET_PATH_ENV}={agent_sock}",
        "-e",
        f"PROFILE_ID={profile_id}",
        "-e",
        f"RUNTIME_INSTANCE_ID={runtime_instance_id}",
        IMAGE_TAG,
        "--profile-id",
        profile_id,
        "--runtime-instance-id",
        runtime_instance_id,
        "--config-snapshot",
        "/run/cbrowser/runtime/snapshot.json",
        "--run-dir",
        "/run/cbrowser/runtime",
        "--user-data-dir",
        f"/data/profiles/{profile_id}/profile",
        "--events-dir",
        f"/data/runtime-events/{profile_id}",
        "--engine-cache-dir",
        "/data/engine-cache",
        "--download-dir",
        "/exchange/downloads",
        "--display",
        display,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30.0)
    cid = proc.stdout.strip()
    return cid


def stop_and_rm_container(name: str) -> None:
    subprocess.run(
        ["docker", "rm", "-f", name],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=15.0,
    )


def save_container_failure_log(container_name: str, test_name: str) -> None:
    """Dump docker logs to dedicated failure file without overwriting."""
    log_file = LOGS_DIR / f"{test_name}_{container_name}_{uuid.uuid4().hex[:6]}.log"
    proc = subprocess.run(
        ["docker", "logs", container_name],
        check=False,
        capture_output=True,
        text=True,
        timeout=15.0,
    )
    log_file.write_text(
        f"STDOUT:\n{proc.stdout}\n\nSTDERR:\n{proc.stderr}\n", encoding="utf-8"
    )


def uds_http(
    container_name: str,
    method: str,
    endpoint: str,
    json_data: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """Execute HTTP request against container UDS via in-container python client."""
    payload_repr = repr(json_data) if json_data is not None else "None"
    script = f"""
import httpx, json, sys
from cbrowser.runtime_agent.socket_root import container_agent_socket_path
transport = httpx.HTTPTransport(uds=container_agent_socket_path())
with httpx.Client(transport=transport, base_url="http://uds") as client:
    if "{method}" == "GET":
        r = client.get("{endpoint}")
    else:
        r = client.post("{endpoint}", json={payload_repr})
    try:
        body = r.json()
    except Exception:
        body = {{"text": r.text}}
    print(json.dumps({{"status_code": r.status_code, "data": body}}))
"""
    proc = subprocess.run(
        ["docker", "exec", container_name, "python3", "-c", script],
        capture_output=True,
        text=True,
        timeout=15.0,
        check=True,
    )
    res = json.loads(proc.stdout.strip())
    return int(res["status_code"]), res["data"]


def wait_for_uds_ready(container_name: str, timeout: float = 35.0) -> dict[str, Any]:
    """Poll container agent.sock /health until ready==True or timeout."""
    start = time.time()
    last_err = None
    while time.time() - start < timeout:
        try:
            status_code, data = uds_http(container_name, "GET", "/health")
            if status_code == 200 and data.get("ready") is True:
                return data
        except Exception as e:  # noqa: BLE001 - polling health readiness
            last_err = type(e).__name__
        time.sleep(0.5)
    logs_proc = subprocess.run(
        ["docker", "logs", container_name],
        check=False,
        capture_output=True,
        text=True,
    )
    print(f"\n--- LOGS: {container_name} ---\n{logs_proc.stdout}\n{logs_proc.stderr}")
    raise TimeoutError(f"{container_name} UDS did not become ready: {last_err}")


def exec_uds_cdp(container_name: str, code_inside: str) -> dict[str, Any]:
    """Execute CDP commands via in-container python script connecting to UDS."""
    wrapped_script = f"""
import asyncio, json, websockets

async def send_cmd(ws, cid, method, params=None, session_id=None, timeout=15.0):
    req = {{"id": cid, "method": method, "params": params or {{}}}}
    if session_id:
        req["sessionId"] = session_id
    await ws.send(json.dumps(req))
    start = asyncio.get_running_loop().time()
    while True:
        remain = timeout - (asyncio.get_running_loop().time() - start)
        if remain <= 0:
            raise TimeoutError(f"Timeout waiting for CDP response cid={{cid}}")
        raw = await asyncio.wait_for(ws.recv(), timeout=remain)
        msg = json.loads(raw)
        if msg.get("id") == cid:
            if "error" in msg:
                err_msg = msg["error"]
                raise RuntimeError(f"CDP command {{cid}} error: {{err_msg}}")
            return msg

async def run():
    from cbrowser.runtime_agent.socket_root import container_agent_socket_path
    sock = container_agent_socket_path()
    async with websockets.unix_connect(sock, "ws://localhost/cdp") as ws:
{code_inside}

asyncio.run(run())
"""
    try:
        proc = subprocess.run(
            ["docker", "exec", container_name, "python3", "-c", wrapped_script],
            capture_output=True,
            text=True,
            timeout=25.0,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print("EXEC_UDS_CDP FAILED:")
        print("STDERR:", e.stderr)
        print("STDOUT:", e.stdout)
        raise

    for line in proc.stdout.splitlines():
        if line.startswith("RESULT:"):
            return json.loads(line[7:])
    raise RuntimeError(
        f"CDP execution completed without outputting RESULT: {proc.stdout}"
    )


@pytest.mark.asyncio
async def test_ac001_persistence_and_dual_profile_isolation(http_server: str) -> None:
    """AC-001: Data persistence across recreation & profile isolation."""
    run_id = uuid.uuid4().hex[:8]
    c_a_name = f"cbrowser-t003-impl-a-{run_id}"
    c_b_name = f"cbrowser-t003-impl-b-{run_id}"
    c_a_recreated = f"cbrowser-t003-impl-a-recreated-{run_id}"
    created_containers: list[str] = []

    dir_a = SCRATCH_ROOT / f"a_{run_id}"
    dir_b = SCRATCH_ROOT / f"b_{run_id}"

    snap_a = dir_a / "snapshot.json"
    snap_b = dir_b / "snapshot.json"
    create_snapshot_file(
        snap_a,
        profile_id="profile_A",
        version=1,
        screen_width=1920,
        screen_height=1080,
        fingerprint_seed=11111,
    )
    create_snapshot_file(
        snap_b,
        profile_id="profile_B",
        version=1,
        screen_width=1920,
        screen_height=1080,
        fingerprint_seed=22222,
    )

    disp_a = f":{100 + (int(run_id[:4], 16) % 300) * 2}"
    disp_b = f":{101 + (int(run_id[:4], 16) % 300) * 2}"

    try:
        run_docker_container(
            name=c_a_name,
            host_profile_dir=dir_a / "profile",
            host_runtime_dir=dir_a / "runtime",
            host_exchange_dir=dir_a / "downloads",
            snapshot_path=snap_a,
            profile_id="profile_A",
            runtime_instance_id=f"inst_a_{run_id}",
            display=disp_a,
        )
        created_containers.append(c_a_name)

        run_docker_container(
            name=c_b_name,
            host_profile_dir=dir_b / "profile",
            host_runtime_dir=dir_b / "runtime",
            host_exchange_dir=dir_b / "downloads",
            snapshot_path=snap_b,
            profile_id="profile_B",
            runtime_instance_id=f"inst_b_{run_id}",
            display=disp_b,
        )
        created_containers.append(c_b_name)

        wait_for_uds_ready(c_a_name, timeout=35.0)
        wait_for_uds_ready(c_b_name, timeout=35.0)

        # 1. Set Cookie A in Profile A via CDP
        url_a = f"{http_server}/set_cookie?val=SECRET_A_COOKIE_999"
        set_cookie_script = f"""
        targets = await send_cmd(ws, 1, "Target.getTargets")
        target_id = targets["result"]["targetInfos"][0]["targetId"]
        attach = await send_cmd(
            ws, 2, "Target.attachToTarget", {{"targetId": target_id, "flatten": True}}
        )
        s = attach["result"]["sessionId"]
        await send_cmd(ws, 3, "Page.navigate", {{"url": "{url_a}"}}, session_id=s)
        await asyncio.sleep(1.0)
        print("RESULT:" + json.dumps({{"status": "ok"}}))
"""
        exec_uds_cdp(c_a_name, set_cookie_script)

        # 2. Check Cookie in Profile B via CDP (Must NOT contain Profile A cookie!)
        check_cookie_script = f"""
        targets = await send_cmd(ws, 1, "Target.getTargets")
        target_id = targets["result"]["targetInfos"][0]["targetId"]
        attach = await send_cmd(
            ws, 2, "Target.attachToTarget", {{"targetId": target_id, "flatten": True}}
        )
        s = attach["result"]["sessionId"]
        resp = await send_cmd(
            ws, 3, "Network.getCookies", {{"urls": ["{http_server}"]}}, session_id=s
        )
        cookies = [c.get("value") for c in resp.get("result", {{}}).get("cookies", [])]
        print("RESULT:" + json.dumps({{"cookies": cookies}}))
"""
        b_res = exec_uds_cdp(c_b_name, check_cookie_script)
        assert "SECRET_A_COOKIE_999" not in b_res.get("cookies", []), (
            "Profile B was contaminated with Profile A cookie!"
        )

        # 3. WebAudio 440Hz vs 880Hz real PCM capture and frequency/crosstalk validation
        # Profile A plays 440Hz, Profile B plays 880Hz
        url_audio_a = f"{http_server}/audio_test.html?freq=440"
        url_audio_b = f"{http_server}/audio_test.html?freq=880"

        audio_script_a = f"""
        targets = await send_cmd(ws, 1, "Target.getTargets")
        target_id = targets["result"]["targetInfos"][0]["targetId"]
        attach = await send_cmd(
            ws, 2, "Target.attachToTarget", {{"targetId": target_id, "flatten": True}}
        )
        s = attach["result"]["sessionId"]
        await send_cmd(ws, 3, "Page.navigate", {{"url": "{url_audio_a}"}}, session_id=s)
        await asyncio.sleep(1.0)
        print("RESULT:" + json.dumps({{"status": "ok"}}))
"""
        exec_uds_cdp(c_a_name, audio_script_a)

        audio_script_b = f"""
        targets = await send_cmd(ws, 1, "Target.getTargets")
        target_id = targets["result"]["targetInfos"][0]["targetId"]
        attach = await send_cmd(
            ws, 2, "Target.attachToTarget", {{"targetId": target_id, "flatten": True}}
        )
        s = attach["result"]["sessionId"]
        await send_cmd(ws, 3, "Page.navigate", {{"url": "{url_audio_b}"}}, session_id=s)
        await asyncio.sleep(1.0)
        print("RESULT:" + json.dumps({{"status": "ok"}}))
"""
        exec_uds_cdp(c_b_name, audio_script_b)

        # Record 1.0s raw PCM from Profile A and Profile B via gst-launch
        gst_cmd_a = [
            "docker",
            "exec",
            "-e",
            "PULSE_SERVER=unix:/pulse/pulse.sock",
            "-e",
            "PULSE_COOKIE=/pulse/pulse.cookie",
            c_a_name,
            "gst-launch-1.0",
            "pulsesrc",
            "device=cbrowser_sink.monitor",
            "num-buffers=50",
            "!",
            "audio/x-raw,format=S16LE,channels=2,rate=48000",
            "!",
            "filesink",
            "location=/tmp/recorded_a.raw",
        ]
        await asyncio.to_thread(subprocess.run, gst_cmd_a, check=True, timeout=15)

        gst_cmd_b = [
            "docker",
            "exec",
            "-e",
            "PULSE_SERVER=unix:/pulse/pulse.sock",
            "-e",
            "PULSE_COOKIE=/pulse/pulse.cookie",
            c_b_name,
            "gst-launch-1.0",
            "pulsesrc",
            "device=cbrowser_sink.monitor",
            "num-buffers=50",
            "!",
            "audio/x-raw,format=S16LE,channels=2,rate=48000",
            "!",
            "filesink",
            "location=/tmp/recorded_b.raw",
        ]
        await asyncio.to_thread(subprocess.run, gst_cmd_b, check=True, timeout=15)

        # Copy PCM files to host scratch
        raw_a = dir_a / "recorded_a.raw"
        raw_b = dir_b / "recorded_b.raw"
        proc_cat_a = await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_a_name, "cat", "/tmp/recorded_a.raw"],
            check=True,
            capture_output=True,
        )
        await asyncio.to_thread(raw_a.write_bytes, proc_cat_a.stdout)
        proc_cat_b = await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_b_name, "cat", "/tmp/recorded_b.raw"],
            check=True,
            capture_output=True,
        )
        await asyncio.to_thread(raw_b.write_bytes, proc_cat_b.stdout)

        # Analyze using audio_analyzer.py
        analyzer_py = (
            Path(__file__).resolve().parents[1]
            / "fixtures"
            / "runtime_probe"
            / "audio_analyzer.py"
        )

        # 3a. Profile A: Positive 440Hz test + Crosstalk check against 880Hz
        res_pcm_a = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                str(analyzer_py),
                str(raw_a),
                "440.0",
                "--rate",
                "48000",
                "--tolerance",
                "0.01",
                "--crosstalk-freq",
                "880.0",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_pcm_a.returncode == 0, (
            f"Profile A 440Hz audio verification failed: {res_pcm_a.stdout}\n"
            f"{res_pcm_a.stderr}"
        )

        # 3b. Profile A: Negative test (must reject 880Hz target on 440Hz signal)
        res_neg_a = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                str(analyzer_py),
                str(raw_a),
                "880.0",
                "--rate",
                "48000",
                "--tolerance",
                "0.01",
                "--expect-fail",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_neg_a.returncode == 0, (
            f"Profile A negative frequency check failed: {res_neg_a.stdout}\n"
            f"{res_neg_a.stderr}"
        )

        # 3c. Profile B: Positive 880Hz test + Crosstalk check against 440Hz
        res_pcm_b = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                str(analyzer_py),
                str(raw_b),
                "880.0",
                "--rate",
                "48000",
                "--tolerance",
                "0.01",
                "--crosstalk-freq",
                "440.0",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_pcm_b.returncode == 0, (
            f"Profile B 880Hz audio verification failed: {res_pcm_b.stdout}\n"
            f"{res_pcm_b.stderr}"
        )

        # 3d. Rate mismatch negative calibration: declaring 48000Hz PCM as 44100Hz must
        # be rejected
        res_rate_mismatch = await asyncio.to_thread(
            subprocess.run,
            [
                sys.executable,
                str(analyzer_py),
                str(raw_a),
                "440.0",
                "--rate",
                "44100",
                "--tolerance",
                "0.01",
                "--expect-fail",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_rate_mismatch.returncode == 0, (
            "Rate mismatch negative calibration failed to reject wrong sampling rate!"
        )

        # 4. Write sentinel in Profile A's user data directory
        sentinel_file = dir_a / "profile" / "sentinel_a.txt"
        sentinel_file.write_text(
            "PERSISTENT_DATA_SURVIVES_RECREATION", encoding="utf-8"
        )

        # Gracefully close browser in Container A to flush Cookies SQLite database
        uds_http(c_a_name, "POST", "/control", {"action": "close"})
        await asyncio.sleep(2.0)

        # 4. RECREATION TEST: Stop Container A and restart with a new container
        stop_and_rm_container(c_a_name)
        run_docker_container(
            name=c_a_recreated,
            host_profile_dir=dir_a / "profile",
            host_runtime_dir=dir_a / "runtime",
            host_exchange_dir=dir_a / "downloads",
            snapshot_path=snap_a,
            profile_id="profile_A",
            runtime_instance_id=f"inst_a_recreated_{run_id}",
            display=disp_a,
        )
        created_containers.append(c_a_recreated)
        wait_for_uds_ready(c_a_recreated, timeout=35.0)

        # Verify persistent cookie still exists in recreated Container A
        check_rec_cookie = f"""
        targets = await send_cmd(ws, 1, "Target.getTargets")
        target_id = targets["result"]["targetInfos"][0]["targetId"]
        attach = await send_cmd(
            ws, 2, "Target.attachToTarget", {{"targetId": target_id, "flatten": True}}
        )
        s = attach["result"]["sessionId"]
        resp = await send_cmd(
            ws, 3, "Network.getCookies", {{"urls": ["{http_server}"]}}, session_id=s
        )
        cookies = [c.get("value") for c in resp.get("result", {{}}).get("cookies", [])]
        print("RESULT:" + json.dumps({{"cookies": cookies}}))
"""
        rec_res = exec_uds_cdp(c_a_recreated, check_rec_cookie)
        assert "SECRET_A_COOKIE_999" in rec_res.get("cookies", []), (
            "Profile A cookie did not survive container recreation!"
        )

        assert sentinel_file.exists(), "Sentinel file disappeared!"
        assert sentinel_file.read_text() == "PERSISTENT_DATA_SURVIVES_RECREATION"
    except Exception:
        for cid in created_containers:
            save_container_failure_log(cid, "test_ac001")
        raise
    finally:
        for cid in created_containers:
            stop_and_rm_container(cid)
        if dir_a.exists():
            shutil.rmtree(dir_a, ignore_errors=True)
        if dir_b.exists():
            shutil.rmtree(dir_b, ignore_errors=True)


@pytest.mark.asyncio
async def test_ac002_subsystem_readiness_and_geometry(http_server: str) -> None:
    """AC-002: Subsystem failure detection and outer window geometry 1920x1080 DPR1."""
    run_id = uuid.uuid4().hex[:8]
    c_name = f"cbrowser-t003-impl-ac002-{run_id}"
    created_containers: list[str] = [c_name]
    dir_work = SCRATCH_ROOT / f"ac002_{run_id}"

    snap_file = dir_work / "snapshot.json"
    create_snapshot_file(
        snap_file,
        profile_id="profile_geo",
        version=1,
        screen_width=1920,
        screen_height=1080,
    )
    disp = f":{120 + (int(run_id[:4], 16) % 300)}"

    try:
        run_docker_container(
            name=c_name,
            host_profile_dir=dir_work / "profile",
            host_runtime_dir=dir_work / "runtime",
            host_exchange_dir=dir_work / "downloads",
            snapshot_path=snap_file,
            profile_id="profile_geo",
            runtime_instance_id=f"inst_geo_{run_id}",
            display=disp,
        )
        health_data = wait_for_uds_ready(c_name, timeout=35.0)

        assert health_data["ready"] is True
        assert health_data["display_ready"] is True
        assert health_data["browser_ready"] is True
        assert health_data["audio_ready"] is True
        assert health_data["cdp_ready"] is True

        # 1. PHYSICAL X11 TOP-LEVEL WINDOW GEOMETRY CHECK via xdotool & xwininfo
        # Must discover Chrome top-level window/WM frame ID (NOT just -root screen)
        # and verify physical width=1920, height=1080 and DPR1
        win_find_proc = await asyncio.to_thread(
            subprocess.run,
            [
                "docker",
                "exec",
                "-e",
                f"DISPLAY={disp}",
                "-e",
                "XAUTHORITY=/run/cbrowser/runtime/Xauthority",
                c_name,
                "xdotool",
                "search",
                "--onlyvisible",
                "--class",
                "chromium",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        wids = [w.strip() for w in win_find_proc.stdout.splitlines() if w.strip()]
        assert len(wids) > 0, "No visible Chromium window found in X11!"
        chrome_wid = wids[0]

        xwin_chrome_proc = await asyncio.to_thread(
            subprocess.run,
            [
                "docker",
                "exec",
                "-e",
                f"DISPLAY={disp}",
                "-e",
                "XAUTHORITY=/run/cbrowser/runtime/Xauthority",
                c_name,
                "xwininfo",
                "-id",
                chrome_wid,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        xwin_out = xwin_chrome_proc.stdout
        assert "Width: 1920" in xwin_out, (
            f"Chrome top-level window Width is not 1920: {xwin_out}"
        )
        assert "Height: 1080" in xwin_out or "-geometry 1920x1080" in xwin_out, (
            f"Chrome top-level window Height is not 1080: {xwin_out}"
        )

        # 2. DOM & WebAudio verification via CDP (BEFORE testing kill-subsystem negative
        # cases)
        eval_script = f"""
        targets = await send_cmd(ws, 1, "Target.getTargets")
        target_id = targets["result"]["targetInfos"][0]["targetId"]
        attach = await send_cmd(
            ws, 2, "Target.attachToTarget", {{"targetId": target_id, "flatten": True}}
        )
        s = attach["result"]["sessionId"]
        url_audio = "{http_server}/audio_test.html"
        await send_cmd(ws, 3, "Page.navigate", {{"url": url_audio}}, session_id=s)
        await asyncio.sleep(1.0)
        expr_p1 = "({{outerWidth: window.outerWidth, innerWidth: window.innerWidth, "
        expr_p2 = "screenWidth: window.screen.width, "
        expr_p3 = "screenHeight: window.screen.height, dpr: window.devicePixelRatio, "
        expr_p4 = "audioRate: window.__audioCtx ? "
        expr_p5 = "window.__audioCtx.sampleRate : null}})"
        expr = expr_p1 + expr_p2 + expr_p3 + expr_p4 + expr_p5
        eval_resp = await send_cmd(
            ws,
            4,
            "Runtime.evaluate",
            {{"expression": expr, "returnByValue": True}},
            session_id=s,
        )
        val = eval_resp["result"]["result"]["value"]
        print("RESULT:" + json.dumps(val))
"""
        metrics = exec_uds_cdp(c_name, eval_script)
        assert metrics["outerWidth"] == 1920, (
            f"Expected outerWidth=1920, got {metrics.get('outerWidth')}"
        )
        assert metrics["screenWidth"] == 1920, (
            f"Expected screenWidth=1920, got {metrics.get('screenWidth')}"
        )
        assert metrics["screenHeight"] == 1080, (
            f"Expected screenHeight=1080, got {metrics.get('screenHeight')}"
        )
        assert metrics["innerWidth"] > 1800, (
            f"Expected innerWidth > 1800, got {metrics.get('innerWidth')}"
        )
        assert metrics["dpr"] == 1, (
            f"Expected devicePixelRatio=1, got {metrics.get('dpr')}"
        )
        assert metrics["audioRate"] == 48000, (
            f"Expected WebAudio sampleRate=48000, got {metrics.get('audioRate')}"
        )

        # 3. SUBSYSTEM FAILURE NEGATIVE TESTS (Display, Pulse, Browser)
        # Sub-test 3a: Kill PulseAudio -> /health must immediately report ready: False
        # and audio_ready: False
        await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "pkill", "-9", "pulseaudio"],
            check=True,
        )
        # Poll with a deadline (t024 AC-007/A28): "immediately" is the
        # 5s bound; the state must actually arrive, not be assumed after
        # a fixed sleep.
        h_pulse_fail_code, h_pulse_fail_data = await poll_until(
            lambda: asyncio.to_thread(uds_http, c_name, "GET", "/health"),
            lambda result: result[0] == 200
            and result[1]["ready"] is False
            and result[1]["audio_ready"] is False,
            timeout=5.0,
            interval=0.1,
            description="health to report PulseAudio failure",
        )

        # Sub-test 3b: Kill Xvfb -> /health must immediately report ready: False and
        # display_ready: False
        await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "pkill", "-9", "Xvfb"],
            check=True,
        )
        h_disp_fail_code, h_disp_fail_data = await poll_until(
            lambda: asyncio.to_thread(uds_http, c_name, "GET", "/health"),
            lambda result: result[0] == 200
            and result[1]["ready"] is False
            and result[1]["display_ready"] is False,
            timeout=5.0,
            interval=0.1,
            description="health to report Xvfb failure",
        )
        assert h_disp_fail_data["status"] in ("degraded", "error")
    except Exception:
        save_container_failure_log(c_name, "test_ac002")
        raise
    finally:
        for cid in created_containers:
            stop_and_rm_container(cid)
        if dir_work.exists():
            shutil.rmtree(dir_work, ignore_errors=True)


@pytest.mark.asyncio
async def test_ac003_controlled_uds_and_allowlist(http_server: str) -> None:
    """AC-003: Controlled UDS access, CDP stream, and RPC allowlist rejection."""
    run_id = uuid.uuid4().hex[:8]
    c_name = f"cbrowser-t003-impl-ac003-{run_id}"
    created_containers: list[str] = [c_name]
    dir_work = SCRATCH_ROOT / f"ac003_{run_id}"

    snap_file = dir_work / "snapshot.json"
    create_snapshot_file(
        snap_file,
        profile_id="profile_uds",
        version=4,
        screen_width=1280,
        screen_height=720,
    )
    disp = f":{130 + (int(run_id[:4], 16) % 300)}"

    try:
        run_docker_container(
            name=c_name,
            host_profile_dir=dir_work / "profile",
            host_runtime_dir=dir_work / "runtime",
            host_exchange_dir=dir_work / "downloads",
            snapshot_path=snap_file,
            profile_id="profile_uds",
            runtime_instance_id=f"inst_uds_{run_id}",
            display=disp,
        )
        wait_for_uds_ready(c_name, timeout=35.0)

        code_cv, data_cv = uds_http(c_name, "GET", "/config_version")
        assert code_cv == 200
        assert data_cv["config_version"] == 4
        assert data_cv["profile_id"] == "profile_uds"

        code_cdp, data_cdp = uds_http(c_name, "GET", "/cdp/version")
        assert code_cdp == 200
        assert "Browser" in data_cdp

        code_bad1, _ = uds_http(
            c_name,
            "POST",
            "/control",
            {"action": "exec_shell", "params": {"cmd": "id"}},
        )
        assert code_bad1 in (400, 422), "Non-whitelisted RPC action was not rejected!"

        code_bad2, _ = uds_http(
            c_name,
            "POST",
            "/control",
            {"action": "read_file", "params": {"path": "/etc/passwd"}},
        )
        assert code_bad2 in (400, 422)

        inspect_proc = await asyncio.to_thread(
            subprocess.run,
            [
                "docker",
                "inspect",
                c_name,
                "--format",
                "{{json .HostConfig.PortBindings}}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        port_bindings = json.loads(inspect_proc.stdout.strip())
        assert port_bindings is None or len(port_bindings) == 0, (
            "Container published ports to host!"
        )

        health_code, health = uds_http(c_name, "GET", "/health")
        assert health_code == 200
        cdp_port = health["details"]["cdp_port"]
        inspect_network = await asyncio.to_thread(
            subprocess.run,
            [
                "docker",
                "inspect",
                c_name,
                "--format",
                "{{json .NetworkSettings.Networks}}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        networks = json.loads(inspect_network.stdout)
        browser_ip = networks[ACTIVE_TEST_NETWORK]["IPAddress"]
        peer_name = f"cbrowser-t003-impl-peer-probe-{run_id}"
        created_containers.append(peer_name)
        script = f"""
import errno, json, socket, urllib.request

with urllib.request.urlopen({http_server!r} + '/download-1.txt', timeout=5) as response:
    assert response.status == 200
with socket.socket() as connection:
    connection.settimeout(2)
    try:
        connection.connect(({browser_ip!r}, {cdp_port!r}))
    except OSError as error:
        assert (
            isinstance(error, TimeoutError) or error.errno == errno.ECONNREFUSED
        ), type(error).__name__
    else:
        raise AssertionError('CDP is directly reachable from the peer network')
print(json.dumps({{'route_positive': True, 'cdp_refused': True}}))
"""
        peer_proc = await asyncio.to_thread(
            subprocess.run,
            [
                "docker",
                "run",
                "--rm",
                "--name",
                peer_name,
                "--network",
                ACTIVE_TEST_NETWORK,
                "--label",
                "cbrowser.task=t003",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--entrypoint",
                "python3",
                IMAGE_TAG,
                "-c",
                script,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        assert json.loads(peer_proc.stdout) == {
            "route_positive": True,
            "cdp_refused": True,
        }
    except Exception:
        save_container_failure_log(c_name, "test_ac003")
        raise
    finally:
        for cid in created_containers:
            stop_and_rm_container(cid)
        if dir_work.exists():
            shutil.rmtree(dir_work, ignore_errors=True)


@pytest.mark.asyncio
async def test_ac004_download_capture_and_recovery(http_server: str) -> None:
    """AC-004: HTTP download capture and recovery after disconnect."""
    run_id = uuid.uuid4().hex[:8]
    c_name = f"cbrowser-t003-impl-ac004-{run_id}"
    created_containers: list[str] = [c_name]
    dir_work = SCRATCH_ROOT / f"ac004_{run_id}"

    snap_file = dir_work / "snapshot.json"
    create_snapshot_file(
        snap_file,
        profile_id="profile_dl",
        version=1,
        screen_width=1280,
        screen_height=720,
    )
    disp = f":{140 + (int(run_id[:4], 16) % 300)}"

    try:
        run_docker_container(
            name=c_name,
            host_profile_dir=dir_work / "profile",
            host_runtime_dir=dir_work / "runtime",
            host_exchange_dir=dir_work / "downloads",
            snapshot_path=snap_file,
            profile_id="profile_dl",
            runtime_instance_id=f"inst_dl_{run_id}",
            display=disp,
        )
        wait_for_uds_ready(c_name, timeout=35.0)

        # 1. Trigger First Download via UDS CDP
        dl_url = f"{http_server}/download_page.html"
        dl1_script = f"""
        targets = await send_cmd(ws, 1, "Target.getTargets")
        target_id = targets["result"]["targetInfos"][0]["targetId"]
        attach = await send_cmd(
            ws, 2, "Target.attachToTarget", {{"targetId": target_id, "flatten": True}}
        )
        s = attach["result"]["sessionId"]
        await send_cmd(ws, 3, "Page.navigate", {{"url": "{dl_url}"}}, session_id=s)
        await asyncio.sleep(1.0)
        click_dl1 = "document.getElementById('dl1').click()"
        await send_cmd(
            ws, 4, "Runtime.evaluate", {{"expression": click_dl1}}, session_id=s
        )
        print("RESULT:" + json.dumps({{"status": "ok"}}))
"""
        exec_uds_cdp(c_name, dl1_script)

        dl_dir = dir_work / "downloads"
        found_file1 = None
        for _ in range(30):
            files = list(dl_dir.glob("*"))
            if files:
                found_file1 = files[0]
                break
            await asyncio.sleep(0.5)

        assert found_file1 is not None, (
            "First download did not land in /exchange/downloads!"
        )
        assert (
            b"E2E_VERIFICATION_CONTENT_FIRST_DOWNLOAD_11111" in found_file1.read_bytes()
        )

        # The first client disconnect must have rearmed capture before we
        # measure the override session's own rearm.
        _, rearm_before_health = await poll_until(
            lambda: asyncio.to_thread(uds_http, c_name, "GET", "/health"),
            lambda result: result[0] == 200
            and result[1]["details"]["rearm_count"] >= 2,
            timeout=5.0,
            interval=0.1,
            description="Agent to rearm after the first automation disconnect",
        )
        rearm_before = rearm_before_health["details"]["rearm_count"]

        # 2. External automation attempts to redirect download capture while
        # holding the connection open.  t030 keeps capture Agent-managed, so
        # the override must be rejected and the intermediate download must
        # still land in the default directory.
        ext_override_dir = "/tmp/external_downloads"
        override_and_mid_dl_script = f"""
        override_params = {{
            "behavior": "allow",
            "downloadPath": "{ext_override_dir}",
            "eventsEnabled": False,
        }}
        override_error = None
        try:
            await send_cmd(
                ws, 99, "Browser.setDownloadBehavior", override_params
            )
        except RuntimeError as exc:
            override_error = str(exc)
        if override_error is None:
            raise AssertionError(
                "Browser.setDownloadBehavior was not rejected by the tunnel"
            )
        if "rejected" not in override_error:
            raise AssertionError(f"Unexpected override error: {{override_error}}")
        # Trigger intermediate download while the automation session is live.
        targets = await send_cmd(ws, 100, "Target.getTargets")
        target_id = targets["result"]["targetInfos"][0]["targetId"]
        attach = await send_cmd(
            ws, 101, "Target.attachToTarget", {{"targetId": target_id, "flatten": True}}
        )
        s = attach["result"]["sessionId"]
        click_mid = "document.getElementById('dl_mid').click()"
        await send_cmd(
            ws, 102, "Runtime.evaluate", {{"expression": click_mid}}, session_id=s
        )
        await asyncio.sleep(2.0)
        print(
            "RESULT:"
            + json.dumps({{"status": "ok", "override_error": override_error}})
        )
"""
        override_res = exec_uds_cdp(c_name, override_and_mid_dl_script)
        assert "rejected" in override_res.get("override_error", ""), (
            f"Override was not rejected by the Agent tunnel: {override_res}"
        )

        # Confirm the intermediate download was still captured by the Agent in
        # the default directory, and nothing leaked into the attempted target.
        intermediate_payload = (
            b"E2E_VERIFICATION_CONTENT_INTERMEDIATE_DOWNLOAD_OVERRIDE_ACTIVE"
        )
        mid_file = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            for candidate in dl_dir.glob("*"):
                if (
                    candidate.is_file()
                    and candidate.read_bytes() == intermediate_payload
                ):
                    mid_file = candidate
                    break
            if mid_file is not None:
                break
            await asyncio.sleep(0.2)
        assert mid_file is not None, (
            "Intermediate download was not captured in /exchange/downloads!"
        )
        current_default_files = [f for f in dl_dir.glob("*") if f.is_file()]
        assert len(current_default_files) == 2, (
            "Expected only the first and intermediate downloads in the default "
            f"directory: {current_default_files}"
        )
        mid_file_proc = await asyncio.to_thread(
            subprocess.run,
            [
                "docker",
                "exec",
                c_name,
                "sh",
                "-c",
                f"ls -A {ext_override_dir} 2>/dev/null || true",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert mid_file_proc.stdout.strip() == "", (
            "Rejected override directory unexpectedly received files: "
            f"{mid_file_proc.stdout}"
        )

        # 3. Disconnection of the external client automatically triggers rearm.
        # Measure it directly instead of assuming it happened.
        await poll_until(
            lambda: asyncio.to_thread(uds_http, c_name, "GET", "/health"),
            lambda result: result[0] == 200
            and result[1]["details"]["rearm_count"] > rearm_before,
            timeout=5.0,
            interval=0.1,
            description="Agent to rearm after the override session disconnected",
        )

        # 4. Trigger Second Formal Download (Proof of Automatic Recovery)
        dl2_script = """
        targets = await send_cmd(ws, 1, "Target.getTargets")
        target_id = targets["result"]["targetInfos"][0]["targetId"]
        attach = await send_cmd(
            ws, 2, "Target.attachToTarget", {"targetId": target_id, "flatten": True}
        )
        s = attach["result"]["sessionId"]
        click_dl2 = "document.getElementById('dl2').click()"
        await send_cmd(
            ws, 3, "Runtime.evaluate", {"expression": click_dl2}, session_id=s
        )
        print("RESULT:" + json.dumps({"status": "ok"}))
"""
        exec_uds_cdp(c_name, dl2_script)

        second_payload = b"E2E_VERIFICATION_CONTENT_SECOND_DOWNLOAD_22222"
        found_file2 = None
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            for candidate in dl_dir.glob("*"):
                if candidate.is_file() and candidate.read_bytes() == second_payload:
                    found_file2 = candidate
                    break
            if found_file2 is not None:
                break
            await asyncio.sleep(0.5)

        assert found_file2 is not None, (
            "Second download did not recover to /exchange/downloads!"
        )

        # Event storage is append-only: begin and completion records have distinct
        # IDs and share a GUID. Require the matching completion, independent of
        # directory/name order, and verify its physical file and byte count.
        deadline = time.monotonic() + 10
        second_event = None
        while time.monotonic() < deadline:
            code_dls, dl_events = uds_http(c_name, "GET", "/events/downloads")
            assert code_dls == 200
            completed = [
                event
                for event in dl_events
                if event["guid"] == found_file2.name
                and event["state"] == "completed"
                and event["suggested_filename"] == "download-2.txt"
            ]
            if completed:
                assert len(completed) == 1
                second_event = completed[0]
                break
            await asyncio.sleep(0.2)
        assert second_event is not None, "Second download completion was not persisted"
        assert (
            second_event["download_path"] == f"/exchange/downloads/{found_file2.name}"
        )
        expected = b"E2E_VERIFICATION_CONTENT_SECOND_DOWNLOAD_22222"
        assert found_file2.read_bytes() == expected
        assert second_event["received_bytes"] == len(expected)
        assert second_event["total_bytes"] == len(expected)
        matching_begin = [
            event
            for event in dl_events
            if event["guid"] == second_event["guid"] and event["state"] == "in_progress"
        ]
        assert len(matching_begin) == 1
        assert matching_begin[0]["event_id"] != second_event["event_id"]
    except Exception:
        save_container_failure_log(c_name, "test_ac004")
        raise
    finally:
        for cid in created_containers:
            stop_and_rm_container(cid)
        if dir_work.exists():
            shutil.rmtree(dir_work, ignore_errors=True)


@pytest.mark.asyncio
async def test_t008_download_reconcile_after_agent_restart(
    http_server: str,
) -> None:
    """t008 AC-002/AC-004: real download, Supervisor forwarder, API ingest, scan."""
    run_id = uuid.uuid4().hex[:8]
    c_name = f"cbrowser-t008-reconcile-{run_id}"
    dir_work = SCRATCH_ROOT / f"t008_{run_id}"
    profile_id = "profile_reconcile"
    artifact_root = dir_work / "artifacts"
    downloads = artifact_root / profile_id / "downloads"
    uploads = artifact_root / profile_id / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    (uploads / "visible.txt").write_text("upload-visible", encoding="utf-8")
    events_dir = dir_work / "runtime-events" / profile_id / "events" / "downloads"

    snap_file = dir_work / "snapshot.json"
    create_snapshot_file(
        snap_file,
        profile_id=profile_id,
        version=1,
        screen_width=1280,
        screen_height=720,
    )
    disp = f":{140 + (int(run_id[:4], 16) % 300)}"
    instance_generation = 0

    api_db = dir_work / "api.db"
    run_database_migrations(api_db)
    engine, maker = create_engine_and_maker(api_db)
    await ProfileRepository(maker).create_profile(
        ProfileConfig(name="Reconcile", fingerprint_seed=1),
        profile_id=profile_id,
    )
    await engine.dispose()

    admin_password = secrets.token_urlsafe(24)
    admin_file = dir_work / "admin.txt"
    admin_file.write_text(admin_password, encoding="utf-8")
    admin_file.chmod(0o600)
    supervisor_token = secrets.token_urlsafe(32)
    supervisor_token_file = dir_work / "supervisor.token"
    supervisor_token_file.write_text(supervisor_token, encoding="utf-8")
    supervisor_token_file.chmod(0o600)
    control_port = _free_port()
    api_port = _free_port()
    origin = "https://127.0.0.1:56661"
    api = _UvicornThread(
        create_app(
            db_path=api_db,
            admin_password_file=admin_file,
            supervisor_token_file=supervisor_token_file,
                        artifacts_root=artifact_root,
            supervisor_url=f"http://127.0.0.1:{control_port}",
        ),
        api_port,
    )
    api.start()
    api_url = f"http://127.0.0.1:{api_port}"
    login_client = httpx.AsyncClient(base_url=api_url, trust_env=False, timeout=10)
    forwarder_client = httpx.AsyncClient(
        base_url=api_url,
        trust_env=False,
        timeout=10,
        headers={"Authorization": f"Bearer {supervisor_token}"},
    )
    login = await login_client.post(
        "/api/v1/auth/login", json={"password": admin_password}
    )
    assert login.status_code == 200, login.text
    session_cookie = login.cookies.get("cbrowser_session")
    assert session_cookie
    login_client.headers["Cookie"] = f"cbrowser_session={session_cookie}"

    async def start() -> None:
        nonlocal instance_generation
        instance_generation += 1
        instance_id = f"inst_reconcile_{run_id}_{instance_generation}"
        previous = (
            f"inst_reconcile_{run_id}_{instance_generation - 1}"
            if instance_generation > 1
            else None
        )
        bind_engine, bind_maker = create_engine_and_maker(api_db)
        try:
            await ProfileRepository(bind_maker).bind_runtime_instance(
                profile_id,
                instance_id,
                config_version=1,
                expected_current_instance=previous,
            )
        finally:
            await bind_engine.dispose()
        profile_dir = dir_work / "profile"
        for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            lock_path = profile_dir / lock_name
            if lock_path.is_symlink() or lock_path.exists():
                lock_path.unlink()
        run_docker_container(
            name=c_name,
            host_profile_dir=profile_dir,
            host_runtime_dir=dir_work / "runtime",
            host_exchange_dir=downloads,
            snapshot_path=snap_file,
            profile_id=profile_id,
            runtime_instance_id=instance_id,
            host_uploads_dir=uploads,
            display=disp,
        )
        wait_for_uds_ready(c_name, timeout=35.0)
        for _ in range(60):
            try:
                cdp_status, _ = uds_http(c_name, "GET", "/cdp/version")
                if cdp_status == 200:
                    break
            except Exception:  # noqa: BLE001 - polling Agent CDP readiness
                pass
            time.sleep(0.5)
        else:
            raise TimeoutError("Agent CDP endpoint did not become ready")

    def scan_events() -> list[dict[str, Any]]:
        code, events = uds_http(c_name, "GET", "/events/downloads")
        assert code == 200
        return [event for event in events if event["event_id"].startswith("dl_scan_")]

    async def artifact_list() -> list[dict[str, Any]]:
        response = await login_client.get(f"/api/v1/profiles/{profile_id}/artifacts")
        assert response.status_code == 200, response.text
        return response.json()

    try:
        await start()
        visible = subprocess.run(
            ["docker", "exec", c_name, "cat", "/exchange/uploads/visible.txt"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        assert visible.stdout == "upload-visible"

        exec_uds_cdp(
            c_name,
            f"""
        targets = await send_cmd(ws, 1, "Target.getTargets")
        target_id = targets["result"]["targetInfos"][0]["targetId"]
        attach = await send_cmd(
            ws, 2, "Target.attachToTarget", {{"targetId": target_id, "flatten": True}}
        )
        s = attach["result"]["sessionId"]
        await send_cmd(
            ws,
            3,
            "Page.navigate",
            {{"url": "{http_server}/download_page.html"}},
            session_id=s,
        )
        await asyncio.sleep(1.0)
        await send_cmd(
            ws, 4, "Runtime.evaluate",
            {{"expression": "document.getElementById('dl1').click()"}}, session_id=s
        )
        print("RESULT:" + json.dumps({{"status": "ok"}}))
""",
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if [f for f in downloads.glob("*") if f.is_file()]:
                break
            await asyncio.sleep(0.5)
        downloaded = [f for f in downloads.glob("*") if f.is_file()]
        assert downloaded, "download missing"

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            completed = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in events_dir.glob("*.json")
            ]
            completed = [
                event for event in completed if event.get("state") == "completed"
            ]
            if completed:
                break
            await asyncio.sleep(0.5)
        assert completed, "completed download event missing"
        forwarder = DownloadArtifactForwarder(dir_work, forwarder_client)
        assert await forwarder.forward_pending() >= 1
        artifacts = await artifact_list()
        assert len(artifacts) == 1
        assert artifacts[0]["name"] == "download-1.txt"
        assert artifacts[0]["kind"] == "download"
        assert (
            artifacts[0]["sha256"]
            == hashlib.sha256(
                b"E2E_VERIFICATION_CONTENT_FIRST_DOWNLOAD_11111"
            ).hexdigest()
        )
        assert not downloaded[0].exists()

        stop_and_rm_container(c_name)
        manual_payload = b"manual-download-without-event"
        (downloads / "manual.csv").write_bytes(manual_payload)

        await start()
        deadline = time.monotonic() + 15
        events: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            events = scan_events()
            if events:
                break
            await asyncio.sleep(0.5)
        manual_events = [
            event for event in events if event["suggested_filename"] == "manual.csv"
        ]
        assert len(manual_events) == 1, f"expected one manual backfill, got {events}"
        assert manual_events[0]["size_bytes"] == len(manual_payload)
        assert manual_events[0]["sha256"] == hashlib.sha256(manual_payload).hexdigest()
        assert manual_events[0]["download_path"] == "/exchange/downloads/manual.csv"
        assert not any(event["download_path"].count("/") > 3 for event in events), (
            f"nested artifact file was scanned: {events}"
        )

        assert await forwarder.forward_pending() >= 1
        artifacts = await artifact_list()
        assert sorted(item["name"] for item in artifacts) == [
            "download-1.txt",
            "manual.csv",
        ]

        stop_and_rm_container(c_name)
        await start()
        await asyncio.sleep(2.0)
        assert scan_events() == events, "Agent restart duplicated the backfill event"
    except Exception:
        save_container_failure_log(c_name, "test_t008_reconcile")
        raise
    finally:
        stop_and_rm_container(c_name)
        await login_client.aclose()
        await forwarder_client.aclose()
        api.stop()
        if dir_work.exists():
            shutil.rmtree(dir_work, ignore_errors=True)


@pytest.mark.asyncio
async def test_ac005_process_lifecycle_agent_restart_and_exit_events(
    http_server: str,
) -> None:
    """AC-005: Decoupled topology, Agent restart, and exit events."""
    run_id = uuid.uuid4().hex[:8]
    c_name = f"cbrowser-t003-impl-ac005-{run_id}"
    created_containers: list[str] = [c_name]
    dir_work = SCRATCH_ROOT / f"ac005_{run_id}"

    snap_file = dir_work / "snapshot.json"
    create_snapshot_file(
        snap_file,
        profile_id="profile_exit",
        version=2,
        screen_width=1280,
        screen_height=720,
    )
    disp = f":{150 + (int(run_id[:4], 16) % 300)}"

    try:
        run_docker_container(
            name=c_name,
            host_profile_dir=dir_work / "profile",
            host_runtime_dir=dir_work / "runtime",
            host_exchange_dir=dir_work / "downloads",
            snapshot_path=snap_file,
            profile_id="profile_exit",
            runtime_instance_id=f"inst_exit_{run_id}",
            display=disp,
        )
        health = wait_for_uds_ready(c_name, timeout=35.0)

        browser_pid = health["details"]["browser_pid"]
        assert browser_pid is not None, "Missing browser PID"

        # Read Chrome start time from in-container /proc/<pid>/stat
        stat_proc1 = await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "cat", f"/proc/{browser_pid}/stat"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15.0,
        )
        starttime_1 = stat_proc1.stdout.split()[21]

        # Read Agent PID
        ps_agent = await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "pgrep", "-f", "cbrowser.runtime_agent.agent"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15.0,
        )
        agent_pid_1 = ps_agent.stdout.strip().splitlines()[0]

        # Navigate to a test page and set a cookie BEFORE killing agent
        cookie_setup_script = """
        targets = await send_cmd(ws, 1, "Target.getTargets")
        target_id = targets["result"]["targetInfos"][0]["targetId"]
        attach = await send_cmd(
            ws, 2, "Target.attachToTarget", {"targetId": target_id, "flatten": True}
        )
        s = attach["result"]["sessionId"]
        await send_cmd(
            ws, 3, "Page.navigate",
            {"url": "data:text/html,<h1>LifecycleTestPage</h1>"}, session_id=s
        )
        await send_cmd(
            ws, 4, "Network.setCookie",
            {"name": "agent_restart_cookie", "value": "ALIVE_ACROSS_RESTART", "url": "http://localhost"},
            session_id=s,
        )
        print("RESULT:" + json.dumps({"status": "ok"}))
"""
        exec_uds_cdp(c_name, cookie_setup_script)

        # KILL AGENT PROCESS ONLY (SIGKILL)
        await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "kill", "-9", agent_pid_1],
            check=True,
            timeout=15.0,
        )

        # The process manager restarts only the killed Agent.

        # Wait for Agent to become ready again on UDS
        health2 = wait_for_uds_ready(c_name, timeout=20.0)
        assert health2["ready"] is True

        # VERIFY CHROME PID AND STARTTIME ARE UNCHANGED
        browser_pid_2 = health2["details"]["browser_pid"]
        assert browser_pid_2 == browser_pid, (
            f"Chrome PID changed! {browser_pid_2} != {browser_pid}"
        )

        stat_proc2 = await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "cat", f"/proc/{browser_pid}/stat"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15.0,
        )
        starttime_2 = stat_proc2.stdout.split()[21]
        assert starttime_2 == starttime_1, (
            f"Chrome starttime changed! {starttime_2} != {starttime_1}"
        )

        # VERIFY PAGE AND COOKIE STILL EXIST AFTER AGENT RESTART
        verify_cookie_script = """
        targets = await send_cmd(ws, 1, "Target.getTargets")
        target_id = targets["result"]["targetInfos"][0]["targetId"]
        attach = await send_cmd(
            ws, 2, "Target.attachToTarget", {"targetId": target_id, "flatten": True}
        )
        s = attach["result"]["sessionId"]
        cookies_resp = await send_cmd(
            ws, 3, "Network.getCookies",
            {"urls": ["http://localhost"]}, session_id=s
        )
        cookies = [
            c.get("value")
            for c in cookies_resp.get("result", {}).get("cookies", [])
        ]
        print("RESULT:" + json.dumps({"cookies": cookies}))
"""
        c_res = exec_uds_cdp(c_name, verify_cookie_script)
        assert "ALIVE_ACROSS_RESTART" in c_res.get("cookies", []), (
            "Cookie was lost during Agent restart!"
        )

        # Send normal close via control RPC
        code_close, _ = uds_http(c_name, "POST", "/control", {"action": "close"})
        assert code_close == 200

        # Wait for Chrome to exit and exit event to be written
        # Events are stored under events/runtime/{runtime_instance_id}/{event_id}.json
        # and authoritative state is under instances/{runtime_instance_id}/state.json
        instance_events_dir = (
            dir_work
            / "runtime-events"
            / "profile_exit"
            / "events"
            / "runtime"
            / f"inst_exit_{run_id}"
        )
        found_exit_evt = None
        for _ in range(30):
            files = list(instance_events_dir.glob("*.json"))
            if files:
                for f in files:
                    ev = json.loads(f.read_text())
                    if ev.get("event_type") == "exit":
                        found_exit_evt = ev
                        break
            if found_exit_evt:
                break
            await asyncio.sleep(0.5)

        assert found_exit_evt is not None, "Normal exit event was not persisted!"
        assert found_exit_evt["exit_code"] == 0, (
            f"Expected exit_code=0, got {found_exit_evt['exit_code']}"
        )
        assert found_exit_evt["exit_reason"] == "normal"
        assert found_exit_evt["config_version"] == 2

        # Check authoritative state.json in instances/{runtime_instance_id}/state.json
        # and discovery cache in persistent events_dir / state.json
        inst_state_file = (
            dir_work
            / "runtime-events"
            / "profile_exit"
            / "instances"
            / f"inst_exit_{run_id}"
            / "state.json"
        )
        assert inst_state_file.exists()
        inst_state_data = json.loads(inst_state_file.read_text())
        assert inst_state_data["state"] == "stopped"
        assert inst_state_data["exit_code"] == 0

        disc_state_file = dir_work / "runtime-events" / "profile_exit" / "state.json"
        assert disc_state_file.exists()
        disc_state_data = json.loads(disc_state_file.read_text())
        assert disc_state_data["state"] == "stopped"
        assert disc_state_data["exit_code"] == 0

        # Verify NO auto-restart of Chrome browser binary
        await asyncio.sleep(2.0)
        proc_check = await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "pgrep", "-f", "chromium-.*/chrome"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15.0,
        )
        assert proc_check.returncode != 0 and not proc_check.stdout.strip(), (
            f"Browser was auto-restarted after normal close! Found: {proc_check.stdout}"
        )

        # Kill the existing Agent and require supervisord to replace that PID.
        old_pid_raw = await asyncio.to_thread(
            subprocess.check_output,
            [
                "docker",
                "exec",
                c_name,
                "pgrep",
                "-f",
                "cbrowser.runtime_agent.agent",
            ],
            text=True,
            timeout=15.0,
        )
        old_pid = old_pid_raw.strip().splitlines()[0]
        await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "kill", "-9", old_pid],
            check=True,
            timeout=15.0,
        )
        deadline = time.monotonic() + 20
        term_health_data = None
        while time.monotonic() < deadline:
            current_res = await asyncio.to_thread(
                subprocess.run,
                [
                    "docker",
                    "exec",
                    c_name,
                    "pgrep",
                    "-f",
                    "cbrowser.runtime_agent.agent",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=15.0,
            )
            current = current_res.stdout.strip().splitlines()
            if current and old_pid not in current:
                try:
                    term_health_code, term_health_data = uds_http(
                        c_name, "GET", "/health"
                    )
                    if term_health_code == 200:
                        break
                except Exception as exc:  # noqa: BLE001 - polling health during terminal agent restart
                    logger.debug(
                        "UDS health poll during restart failed: %s",
                        type(exc).__name__,
                    )
            await asyncio.sleep(0.3)
        else:
            raise AssertionError("Terminal Agent did not restart under supervisord")
        assert term_health_data is not None
        assert term_health_data["ready"] is False
        assert term_health_data["details"]["state"] == "stopped"

        # Check that Chrome was not mistakenly restarted
        proc_check2 = await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "pgrep", "-f", "chromium-.*/chrome"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15.0,
        )
        assert proc_check2.returncode != 0 and not proc_check2.stdout.strip(), (
            f"Browser incorrectly launched during replay! Found: {proc_check2.stdout}"
        )
    except Exception:
        save_container_failure_log(c_name, "test_ac005")
        raise
    finally:
        for cid in created_containers:
            stop_and_rm_container(cid)
        if dir_work.exists():
            shutil.rmtree(dir_work, ignore_errors=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kill_target,expected_event_type,expected_event_exit_code,expected_state,expected_state_exit_code,expected_exit_reason",
    [
        ("chrome", "exit", 137, "stopped", 137, "abnormal"),
        ("driver", "lifecycle", None, "error", 0, "process_observation_lost"),
    ],
)
async def test_ac005_abnormal_termination_lifecycle_and_agent_replay(
    kill_target: str,
    expected_event_type: str,
    expected_event_exit_code: int | None,
    expected_state: str,
    expected_state_exit_code: int | None,
    expected_exit_reason: str,
    http_server: str,
) -> None:
    """AC-005 Regression: Real SIGKILL Chrome (137) and SDK driver loss (lifecycle).

    Verifies that:
    1. Direct SIGKILL of Chrome produces exit_code 137, abnormal, stopped.
    2. SDK Node driver loss produces lifecycle event with exit_code None (not fake 0),
       state 'error', reason 'process_observation_lost', cascade 0 in payload.
    3. Events and states are written to authoritative instance paths with valid ID.
    4. supervisord auto-restarts Agent upon SIGKILL without launching Chrome.
    5. Agent replays the persisted terminal facts with identical event_id retained.
    """
    run_id = uuid.uuid4().hex[:8]
    c_name = f"cbrowser-t003-impl-ac005-{kill_target}-{run_id}"
    created_containers: list[str] = [c_name]
    dir_work = SCRATCH_ROOT / f"ac005_{kill_target}_{run_id}"

    profile_id = f"profile_abnormal_{kill_target}"
    runtime_instance_id = f"inst_abnormal_{kill_target}_{run_id}"
    config_version = 3

    snap_file = dir_work / "snapshot.json"
    create_snapshot_file(
        snap_file,
        profile_id=profile_id,
        version=config_version,
        screen_width=1280,
        screen_height=720,
    )
    disp = f":{180 + (int(run_id[:4], 16) % 300)}"

    try:
        run_docker_container(
            name=c_name,
            host_profile_dir=dir_work / "profile",
            host_runtime_dir=dir_work / "runtime",
            host_exchange_dir=dir_work / "downloads",
            snapshot_path=snap_file,
            profile_id=profile_id,
            runtime_instance_id=runtime_instance_id,
            display=disp,
        )
        health = wait_for_uds_ready(c_name, timeout=35.0)
        assert health["ready"] is True

        browser_pid = health["details"]["browser_pid"]
        assert browser_pid is not None, "Missing browser PID"

        # Read Chrome start time from in-container /proc/<pid>/stat
        stat_proc1 = await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "cat", f"/proc/{browser_pid}/stat"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15.0,
        )
        starttime_1 = stat_proc1.stdout.split()[21]
        assert starttime_1 is not None

        # Read Agent PID
        ps_agent1 = await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "pgrep", "-f", "cbrowser.runtime_agent.agent"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15.0,
        )
        agent_pid_1 = ps_agent1.stdout.strip().splitlines()[0]

        # Trigger target process termination
        if kill_target == "chrome":
            # Send SIGKILL to real Chrome PID
            await asyncio.to_thread(
                subprocess.run,
                ["docker", "exec", c_name, "kill", "-9", str(browser_pid)],
                check=True,
                timeout=15.0,
            )
        elif kill_target == "driver":
            # Discover and kill the Playwright node driver process
            ps_driver = await asyncio.to_thread(
                subprocess.run,
                ["docker", "exec", c_name, "pgrep", "-f", "playwright/driver/node"],
                capture_output=True,
                text=True,
                check=True,
                timeout=15.0,
            )
            driver_pid = ps_driver.stdout.strip().splitlines()[0]
            await asyncio.to_thread(
                subprocess.run,
                ["docker", "exec", c_name, "kill", "-9", driver_pid],
                check=True,
                timeout=15.0,
            )
        else:
            raise ValueError(f"Unknown kill_target: {kill_target}")

        # Bounded wait for terminal event under events/runtime/{instance_id}
        instance_events_dir = (
            dir_work
            / "runtime-events"
            / profile_id
            / "events"
            / "runtime"
            / runtime_instance_id
        )
        terminal_event = None
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if instance_events_dir.exists():
                files = list(instance_events_dir.glob("*.json"))
                if files:
                    for f in files:
                        ev = json.loads(f.read_text(encoding="utf-8"))
                        if ev.get("event_type") == expected_event_type:
                            terminal_event = ev
                            break
            if terminal_event:
                break
            await asyncio.sleep(0.3)

        assert terminal_event is not None, (
            f"Terminal event of type {expected_event_type} not found"
        )
        expected_event_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"cbrowser/{profile_id}/{runtime_instance_id}/exit",
            )
        )
        assert terminal_event["event_id"] == expected_event_id, (
            f"Event ID mismatch: {terminal_event['event_id']} != {expected_event_id}"
        )
        assert terminal_event["profile_id"] == profile_id
        assert terminal_event["runtime_instance_id"] == runtime_instance_id
        assert terminal_event["config_version"] == config_version
        assert terminal_event["exit_code"] == expected_event_exit_code, (
            f"Expected code {expected_event_exit_code}, "
            f"got {terminal_event['exit_code']}"
        )
        assert terminal_event["exit_reason"] == expected_exit_reason

        if kill_target == "driver":
            # For driver loss: payload records cascade 0, but formal exit_code is None
            assert terminal_event["payload"].get("exit_code") == 0
            assert (
                terminal_event["payload"].get("exit_reason")
                == "process_observation_lost"
            )

        # Check authoritative instance state.json
        instance_state_file = (
            dir_work
            / "runtime-events"
            / profile_id
            / "instances"
            / runtime_instance_id
            / "state.json"
        )
        assert instance_state_file.exists(), (
            f"Instance state missing: {instance_state_file}"
        )
        inst_state = json.loads(instance_state_file.read_text(encoding="utf-8"))
        assert inst_state["profile_id"] == profile_id
        assert inst_state["runtime_instance_id"] == runtime_instance_id
        assert inst_state["config_version"] == config_version
        assert inst_state["state"] == expected_state, (
            f"Expected instance state {expected_state}, got {inst_state['state']}"
        )
        assert inst_state["exit_code"] == expected_state_exit_code
        assert inst_state["exit_reason"] == expected_exit_reason

        # Discovery cache in events root
        disc_state_file = dir_work / "runtime-events" / profile_id / "state.json"
        assert disc_state_file.exists()
        disc_state = json.loads(disc_state_file.read_text(encoding="utf-8"))
        assert disc_state["profile_id"] == profile_id
        assert disc_state["runtime_instance_id"] == runtime_instance_id
        assert disc_state["state"] == expected_state
        assert disc_state["exit_code"] == expected_state_exit_code

        # Verify NO automatic browser restart
        await asyncio.sleep(2.0)
        proc_check1 = await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "pgrep", "-f", "chromium-.*/chrome"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15.0,
        )
        assert proc_check1.returncode != 0 and not proc_check1.stdout.strip(), (
            f"Browser auto-restarted after {kill_target} kill! "
            f"PIDs: {proc_check1.stdout}"
        )

        # Pre-restart health verification
        pre_code, pre_health = uds_http(c_name, "GET", "/health")
        assert pre_code == 200
        assert pre_health["ready"] is False
        assert pre_health["status"] == "error"
        assert pre_health["details"]["state"] == expected_state

        # KILL AGENT (SIGKILL) and verify supervisord autoAgent restart & replay
        await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "kill", "-9", agent_pid_1],
            check=True,
            timeout=15.0,
        )

        restart_deadline = time.monotonic() + 20.0
        new_agent_pid = None
        replay_health = None
        while time.monotonic() < restart_deadline:
            ps_new = await asyncio.to_thread(
                subprocess.run,
                [
                    "docker",
                    "exec",
                    c_name,
                    "pgrep",
                    "-f",
                    "cbrowser.runtime_agent.agent",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=15.0,
            )
            pids = ps_new.stdout.strip().splitlines()
            if pids and agent_pid_1 not in pids:
                new_agent_pid = pids[0]
                try:
                    rep_code, rep_data = uds_http(c_name, "GET", "/health")
                    if rep_code == 200:
                        replay_health = rep_data
                        break
                except Exception as exc:  # noqa: BLE001 - polling health during agent replay
                    logger.debug(
                        "UDS health poll during replay failed: %s",
                        type(exc).__name__,
                    )
            await asyncio.sleep(0.3)

        assert new_agent_pid is not None, "supervisord failed to restart Agent process"
        assert new_agent_pid != agent_pid_1, "Agent PID did not change across restart"
        assert replay_health is not None, (
            "Restarted Agent UDS did not become accessible"
        )

        # Replay assertions: terminal state reflected without browser relaunch
        assert replay_health["ready"] is False
        assert replay_health["status"] == "error"
        assert replay_health["profile_id"] == profile_id
        assert replay_health["runtime_instance_id"] == runtime_instance_id
        assert replay_health["config_version"] == config_version
        assert replay_health["details"]["state"] == expected_state
        assert replay_health["details"]["exit_code"] == expected_state_exit_code
        assert replay_health["details"]["exit_reason"] == expected_exit_reason

        # Re-verify through UDS event API that explicit same event_id was retained
        ev_code, ev_list = uds_http(c_name, "GET", "/events/runtime")
        assert ev_code == 200
        matching = [e for e in ev_list if e.get("event_id") == expected_event_id]
        assert len(matching) == 1, (
            f"Expected retained event {expected_event_id} in {ev_list}"
        )
        assert matching[0]["profile_id"] == profile_id
        assert matching[0]["runtime_instance_id"] == runtime_instance_id
        assert matching[0]["config_version"] == config_version
        assert matching[0]["event_type"] == expected_event_type
        assert matching[0]["exit_code"] == expected_event_exit_code
        assert matching[0]["exit_reason"] == expected_exit_reason

        # Final check that Chrome was not restarted during agent replay
        proc_check2 = await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "pgrep", "-f", "chromium-.*/chrome"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15.0,
        )
        assert proc_check2.returncode != 0 and not proc_check2.stdout.strip(), (
            f"Browser incorrectly launched during replay! Found: {proc_check2.stdout}"
        )
    except Exception:
        save_container_failure_log(c_name, f"test_ac005_{kill_target}")
        raise
    finally:
        for cid in created_containers:
            stop_and_rm_container(cid)
        if dir_work.exists():
            shutil.rmtree(dir_work, ignore_errors=True)


@pytest.mark.asyncio
async def test_ac006_minimal_privileges_and_access_control(http_server: str) -> None:
    """AC-006: Non-root UID 1000, read-only rootfs, no docker.sock, and stream auth."""
    run_id = uuid.uuid4().hex[:8]
    c_name = f"cbrowser-t003-impl-ac006-{run_id}"
    created_containers: list[str] = [c_name]
    dir_work = SCRATCH_ROOT / f"ac006_{run_id}"

    snap_file = dir_work / "snapshot.json"
    create_snapshot_file(
        snap_file,
        profile_id="profile_sec",
        version=1,
        screen_width=1280,
        screen_height=720,
    )
    disp = f":{160 + (int(run_id[:4], 16) % 300)}"

    try:
        run_docker_container(
            name=c_name,
            host_profile_dir=dir_work / "profile",
            host_runtime_dir=dir_work / "runtime",
            host_exchange_dir=dir_work / "downloads",
            snapshot_path=snap_file,
            profile_id="profile_sec",
            runtime_instance_id=f"inst_sec_{run_id}",
            display=disp,
        )
        wait_for_uds_ready(c_name, timeout=35.0)

        # 1. Non-root user check (UID 1000, GID 1000)
        id_proc = await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "id"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "uid=1000(cbrowser)" in id_proc.stdout
        assert "gid=1000(cbrowser)" in id_proc.stdout

        # 2. Read-only rootfs check
        ro_proc = await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "touch", "/test_read_only"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert ro_proc.returncode != 0, "Rootfs was writable!"
        assert "Read-only file system" in ro_proc.stderr

        # 3. No Docker socket check
        sock_proc = await asyncio.to_thread(
            subprocess.run,
            ["docker", "exec", c_name, "ls", "-la", "/var/run/docker.sock"],
            check=False,
            capture_output=True,
            text=True,
        )
        assert sock_proc.returncode != 0, "Docker socket was present in container!"

        # 4. Display authorization test from external probe
        xauth_file = dir_work / "runtime" / "Xauthority"
        pulse_cookie = dir_work / "runtime" / "pulse" / "pulse.cookie"
        disp_num = disp.lstrip(":")
        x11_sock = dir_work / "runtime" / "x11" / f"X{disp_num}"
        pulse_sock = dir_work / "runtime" / "pulse" / "pulse.sock"

        assert xauth_file.exists()
        assert pulse_cookie.exists()
        assert x11_sock.exists()
        assert pulse_sock.exists()
        assert stat.S_IMODE(xauth_file.stat().st_mode) == 0o600
        assert stat.S_IMODE(pulse_cookie.stat().st_mode) == 0o600

        inspect_hn_proc = await asyncio.to_thread(
            subprocess.run,
            ["docker", "inspect", "-f", "{{.Config.Hostname}}", c_name],
            capture_output=True,
            text=True,
            check=True,
            timeout=15.0,
        )
        container_hn = inspect_hn_proc.stdout.strip()

        auth_probe_name = f"cbrowser-t003-impl-auth-probe-{run_id}"
        created_containers.append(auth_probe_name)
        auth_proc = await asyncio.to_thread(
            subprocess.run,
            [
                "docker",
                "run",
                "--rm",
                "--name",
                auth_probe_name,
                "--label",
                "cbrowser.task=t003",
                "--user",
                "1000:1000",
                "-h",
                container_hn,
                "--network",
                "none",
                "-v",
                f"{xauth_file}:/tmp/stream_xauth:ro",
                "-v",
                f"{x11_sock}:/tmp/.X11-unix/X{disp_num}",
                "-e",
                f"DISPLAY={disp}",
                "-e",
                "XAUTHORITY=/tmp/stream_xauth",
                "--entrypoint",
                "xdpyinfo",
                IMAGE_TAG,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=20.0,
        )
        assert auth_proc.returncode == 0, (
            f"Authorized client failed to connect to X11: {auth_proc.stderr}"
        )

        unauth_probe_name = f"cbrowser-t003-impl-unauth-probe-{run_id}"
        created_containers.append(unauth_probe_name)
        fake_xauth = dir_work / "fake_xauth"
        fake_xauth.write_bytes(os.urandom(32))
        unauth_proc = await asyncio.to_thread(
            subprocess.run,
            [
                "docker",
                "run",
                "--rm",
                "--name",
                unauth_probe_name,
                "--label",
                "cbrowser.task=t003",
                "--user",
                "1000:1000",
                "-h",
                container_hn,
                "--network",
                "none",
                "-v",
                f"{fake_xauth}:/tmp/stream_xauth:ro",
                "-v",
                f"{x11_sock}:/tmp/.X11-unix/X{disp_num}",
                "-e",
                f"DISPLAY={disp}",
                "-e",
                "XAUTHORITY=/tmp/stream_xauth",
                "--entrypoint",
                "xdpyinfo",
                IMAGE_TAG,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=20.0,
        )
        assert unauth_proc.returncode != 0, "Invalid Xauthority was accepted"
        assert (
            "Authorization required" in unauth_proc.stderr
            or "Invalid MIT-MAGIC-COOKIE" in unauth_proc.stderr
        ), unauth_proc.stderr

        # 5. MIT-SHM Authorization & Cross-IPC Isolation Boundary Tests
        # 5a. POSITIVE CASE: Same-profile stream client with container IPC shares
        # MIT-SHM successfully
        stream_shm_name = f"cbrowser-t003-impl-stream-shm-{run_id}"
        created_containers.append(stream_shm_name)
        shm_pos_proc = await asyncio.to_thread(
            subprocess.run,
            [
                "docker",
                "run",
                "--rm",
                "--name",
                stream_shm_name,
                "--label",
                "cbrowser.task=t003",
                "--user",
                "1000:1000",
                "-h",
                container_hn,
                "--ipc",
                f"container:{c_name}",
                "-v",
                f"{xauth_file}:/tmp/stream_xauth:ro",
                "-v",
                f"{x11_sock}:/tmp/.X11-unix/X{disp_num}",
                "-e",
                f"DISPLAY={disp}",
                "-e",
                "XAUTHORITY=/tmp/stream_xauth",
                "--entrypoint",
                "/usr/local/bin/test_mitshm",
                IMAGE_TAG,
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=20.0,
        )
        assert shm_pos_proc.returncode == 0, (
            f"Positive MIT-SHM test failed: {shm_pos_proc.stderr}"
        )
        assert (
            "Positive MIT-SHM verification completed successfully"
            in shm_pos_proc.stdout
        )

        # 5b. NEGATIVE CASE: Cross-IPC Boundary: client has correct Xauthority but
        # independent IPC namespace (isolated peer container).
        # Must be rejected with BadAccess (error 10) by X server
        peer_ipc_name = f"cbrowser-t003-impl-peer-ipc-{run_id}"
        dir_peer = SCRATCH_ROOT / f"ac006_peer_{run_id}"
        snap_peer = dir_peer / "snapshot.json"
        create_snapshot_file(
            snap_peer,
            profile_id="profile_peer",
            version=1,
            screen_width=1280,
            screen_height=720,
        )
        disp_peer = f":{170 + (int(run_id[:4], 16) % 300)}"
        run_docker_container(
            name=peer_ipc_name,
            host_profile_dir=dir_peer / "profile",
            host_runtime_dir=dir_peer / "runtime",
            host_exchange_dir=dir_peer / "downloads",
            snapshot_path=snap_peer,
            profile_id="profile_peer",
            runtime_instance_id=f"inst_peer_{run_id}",
            display=disp_peer,
        )
        created_containers.append(peer_ipc_name)
        wait_for_uds_ready(peer_ipc_name, timeout=35.0)

        cross_ipc_name = f"cbrowser-t003-impl-cross-ipc-{run_id}"
        created_containers.append(cross_ipc_name)
        shm_neg_proc = await asyncio.to_thread(
            subprocess.run,
            [
                "docker",
                "run",
                "--rm",
                "--name",
                cross_ipc_name,
                "--label",
                "cbrowser.task=t003",
                "--user",
                "1000:1000",
                "-h",
                container_hn,
                "--ipc",
                f"container:{peer_ipc_name}",
                "-v",
                f"{xauth_file}:/tmp/stream_xauth:ro",
                "-v",
                f"{x11_sock}:/tmp/.X11-unix/X{disp_num}",
                "-e",
                f"DISPLAY={disp}",
                "-e",
                "XAUTHORITY=/tmp/stream_xauth",
                "--entrypoint",
                "/usr/local/bin/test_mitshm",
                IMAGE_TAG,
                "--expect-shm-denied",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=20.0,
        )
        assert shm_neg_proc.returncode == 0, (
            f"Cross-IPC negative MIT-SHM check failed: {shm_neg_proc.stderr}"
        )
        assert (
            "CONFIRMED_SHM_DENIED: XShmAttach rejected with BadAccess"
            in shm_neg_proc.stdout
        )

        # 6. PulseAudio Authorization & UID Boundaries (d011)
        # 6a. POSITIVE: Authorized client with UID 1000 and valid cookie
        pulse_probe_uid1000 = f"cbrowser-t003-impl-pulse-pos-{run_id}"
        created_containers.append(pulse_probe_uid1000)
        pulse_pos_proc = await asyncio.to_thread(
            subprocess.run,
            [
                "docker",
                "run",
                "--rm",
                "--name",
                pulse_probe_uid1000,
                "--label",
                "cbrowser.task=t003",
                "--user",
                "1000:1000",
                "-v",
                f"{pulse_sock}:/pulse/pulse.sock",
                "-v",
                f"{pulse_cookie}:/pulse/pulse.cookie:ro",
                "-e",
                "PULSE_SERVER=unix:/pulse/pulse.sock",
                "-e",
                "PULSE_COOKIE=/pulse/pulse.cookie",
                "--entrypoint",
                "pactl",
                IMAGE_TAG,
                "info",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=20.0,
        )
        assert pulse_pos_proc.returncode == 0, (
            f"Authorized Pulse client failed: {pulse_pos_proc.stderr}"
        )
        assert (
            "Server Name: pulseaudio" in pulse_pos_proc.stdout
            or "Server String:" in pulse_pos_proc.stdout
        )

        # 6b. NEGATIVE: UID 1001 with wrong cookie rejected with Access denied
        pulse_probe_uid1001 = f"cbrowser-t003-impl-pulse-probe-{run_id}"
        created_containers.append(pulse_probe_uid1001)
        fake_cookie_file = dir_work / "fake_pulse.cookie"
        fake_cookie_file.write_bytes(os.urandom(256))
        pulse_neg_proc = await asyncio.to_thread(
            subprocess.run,
            [
                "docker",
                "run",
                "--rm",
                "--name",
                pulse_probe_uid1001,
                "--label",
                "cbrowser.task=t003",
                "--user",
                "1001:1000",
                "-v",
                f"{pulse_sock}:/pulse/pulse.sock",
                "-v",
                f"{fake_cookie_file}:/pulse/pulse.cookie:ro",
                "-e",
                "PULSE_SERVER=unix:/pulse/pulse.sock",
                "-e",
                "PULSE_COOKIE=/pulse/pulse.cookie",
                "--entrypoint",
                "pactl",
                IMAGE_TAG,
                "info",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=20.0,
        )
        assert pulse_neg_proc.returncode != 0, (
            "PulseAudio accepted invalid cookie under UID 1001!"
        )
        assert "Access denied" in pulse_neg_proc.stderr, (
            f"Expected 'Access denied' error from PulseAudio, "
            f"got: {pulse_neg_proc.stderr}"
        )
    except Exception:
        save_container_failure_log(c_name, "test_ac006")
        raise
    finally:
        for cid in created_containers:
            stop_and_rm_container(cid)
        if dir_work.exists():
            shutil.rmtree(dir_work, ignore_errors=True)
        if (SCRATCH_ROOT / f"ac006_peer_{run_id}").exists():
            shutil.rmtree(SCRATCH_ROOT / f"ac006_peer_{run_id}", ignore_errors=True)


@pytest.mark.asyncio
async def test_t013_state_copy_restores_cookies_in_clone(http_server: str) -> None:
    """t013 AC-002/AC-004: stopped source state copy, clone launches with cookies."""
    run_id = uuid.uuid4().hex[:8]
    dir_work = SCRATCH_ROOT / f"t013_{run_id}"
    profiles_root = dir_work / "profiles"
    source_dir = profiles_root / "source" / "profile"
    source_dir.mkdir(parents=True)
    db = dir_work / "profiles.db"
    run_database_migrations(db)
    engine, maker = create_engine_and_maker(db)
    repo = ProfileRepository(maker)
    await repo.create_profile(
        ProfileConfig(name="Cookie Source", fingerprint_seed=999),
        profile_id="source",
        user_data_dir=str(source_dir),
    )
    admin_password = secrets.token_urlsafe(24)
    admin_file = dir_work / "admin.txt"
    admin_file.write_text(admin_password, encoding="utf-8")
    admin_file.chmod(0o600)

    source_name = f"cbrowser-t013-source-{run_id}"
    clone_name = f"cbrowser-t013-clone-{run_id}"
    snap = dir_work / "snapshot.json"
    create_snapshot_file(
        snap,
        profile_id="source",
        version=1,
        screen_width=1280,
        screen_height=720,
    )
    display_number = 140 + (int(run_id[:4], 16) % 300)
    try:
        run_docker_container(
            name=source_name,
            host_profile_dir=source_dir,
            host_runtime_dir=dir_work / "source-runtime",
            host_exchange_dir=dir_work / "source-downloads",
            snapshot_path=snap,
            profile_id="source",
            runtime_instance_id=f"inst_source_{run_id}",
            display=f":{display_number}",
        )
        wait_for_uds_ready(source_name, timeout=35.0)
        exec_uds_cdp(
            source_name,
            f"""
        targets = await send_cmd(ws, 1, "Target.getTargets")
        target_id = targets["result"]["targetInfos"][0]["targetId"]
        attach = await send_cmd(
            ws, 2, "Target.attachToTarget", {{"targetId": target_id, "flatten": True}}
        )
        s = attach["result"]["sessionId"]
        await send_cmd(
            ws,
            3,
            "Network.setCookie",
            {{
                "name": "t013cookie",
                "value": "yes",
                "url": "{http_server}/",
            }},
            session_id=s,
        )
        print("RESULT:" + json.dumps({{"status": "ok"}}))
""",
        )
        subprocess.run(
            ["docker", "stop", "-t", "20", source_name],
            capture_output=True,
            timeout=30,
            check=False,
        )
        stop_and_rm_container(source_name)

        api_port = _free_port()
        origin = "https://127.0.0.1:56661"
        api = _UvicornThread(
            create_app(
                db_path=db,
                admin_password_file=admin_file,
                                artifacts_root=dir_work / "artifacts",
            ),
            api_port,
        )
        api.start()
        api_url = f"http://127.0.0.1:{api_port}"
        api_client = httpx.AsyncClient(base_url=api_url, trust_env=False, timeout=10)
        login = await api_client.post(
            "/api/v1/auth/login", json={"password": admin_password}
        )
        assert login.status_code == 200, login.text
        session_cookie = login.cookies.get("cbrowser_session")
        assert session_cookie
        api_headers = {
            "X-CSRF-Token": login.json()["csrf_token"],
            "Origin": origin,
            "Cookie": f"cbrowser_session={session_cookie}",
            "Idempotency-Key": f"duplicate-{run_id}",
        }
        duplicate_response = await api_client.post(
            "/api/v1/profiles/source/duplicate",
            json={"include_browser_state": True},
            headers=api_headers,
        )
        assert duplicate_response.status_code == 201, duplicate_response.text
        clone_payload = duplicate_response.json()
        clone_id = clone_payload["id"]
        assert clone_payload["current_config_version"] == 1
        assert clone_payload["fingerprint_seed"] == 999
        clone_dir = Path(clone_payload["user_data_dir"])
        assert clone_dir.is_dir()
        assert (clone_dir / "Cookies").is_file() or (
            clone_dir / "Default" / "Cookies"
        ).is_file()

        clone_snap = dir_work / "clone-snapshot.json"
        create_snapshot_file(
            clone_snap,
            profile_id=clone_id,
            version=1,
            screen_width=1280,
            screen_height=720,
        )
        run_docker_container(
            name=clone_name,
            host_profile_dir=clone_dir,
            host_runtime_dir=dir_work / "clone-runtime",
            host_exchange_dir=dir_work / "clone-downloads",
            snapshot_path=clone_snap,
            profile_id=clone_id,
            runtime_instance_id=f"inst_clone_{run_id}",
            display=f":{display_number + 1}",
        )
        wait_for_uds_ready(clone_name, timeout=35.0)
        result = exec_uds_cdp(
            clone_name,
            f"""
        targets = await send_cmd(ws, 1, "Target.getTargets")
        target_id = targets["result"]["targetInfos"][0]["targetId"]
        attach = await send_cmd(
            ws, 2, "Target.attachToTarget", {{"targetId": target_id, "flatten": True}}
        )
        s = attach["result"]["sessionId"]
        cookies = await send_cmd(
            ws,
            3,
            "Network.getCookies",
            {{"urls": ["{http_server}/"]}},
            session_id=s,
        )
        print("RESULT:" + json.dumps({{"cookies": cookies}}))
""",
        )
        cookies = result["cookies"].get("result", {}).get("cookies", [])
        assert any(
            item.get("name") == "t013cookie" and item.get("value") == "yes"
            for item in cookies
        ), result["cookies"]
        assert (source_dir / "Cookies").is_file() or (
            source_dir / "Default" / "Cookies"
        ).is_file()
        reset_response = await api_client.post(
            "/api/v1/profiles/source/reset",
            json={"confirm": True},
            headers={**api_headers, "Idempotency-Key": f"reset-{run_id}"},
        )
        assert reset_response.status_code == 200, reset_response.text
        assert reset_response.json()["fingerprint_seed"] != 999
        assert list(source_dir.iterdir()) == []
    finally:
        stop_and_rm_container(source_name)
        stop_and_rm_container(clone_name)
        await engine.dispose()
        if "api" in locals():
            api.stop()
        if "api_client" in locals():
            await api_client.aclose()
        if dir_work.exists():
            shutil.rmtree(dir_work, ignore_errors=True)


@pytest.mark.asyncio
async def test_p014_file_input_opens_chooser_with_uploads_bookmark(
    http_server: str,
) -> None:
    """p014: a page's file input opens the native chooser, bookmarked to uploads."""
    run_id = uuid.uuid4().hex[:8]
    c_name = f"cbrowser-p014-picker-{run_id}"
    dir_work = SCRATCH_ROOT / f"p014_{run_id}"
    uploads = dir_work / "uploads"
    (uploads / f"artifact_{run_id}").mkdir(parents=True)
    (uploads / f"artifact_{run_id}" / "demo.txt").write_text("p014", encoding="utf-8")
    snap_file = dir_work / "snapshot.json"
    create_snapshot_file(
        snap_file,
        profile_id="profile_picker",
        version=1,
        screen_width=1280,
        screen_height=720,
    )
    disp = f":{160 + (int(run_id[:4], 16) % 300)}"
    x_env = [
        "-e",
        f"DISPLAY={disp}",
        "-e",
        "XAUTHORITY=/run/cbrowser/runtime/Xauthority",
    ]

    def visible_window_names() -> list[str]:
        ids = subprocess.run(
            ["docker", "exec", *x_env, c_name, "xdotool", "search", "--onlyvisible",
             "--name", "."],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.split()
        names = []
        for wid in ids:
            names.append(
                subprocess.run(
                    ["docker", "exec", *x_env, c_name, "xdotool", "getwindowname",
                     wid],
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout.strip()
            )
        return names

    try:
        run_docker_container(
            name=c_name,
            host_profile_dir=dir_work / "profile",
            host_runtime_dir=dir_work / "runtime",
            host_exchange_dir=dir_work / "downloads",
            host_uploads_dir=uploads,
            snapshot_path=snap_file,
            profile_id="profile_picker",
            runtime_instance_id=f"inst_picker_{run_id}",
            display=disp,
        )
        wait_for_uds_ready(c_name, timeout=35.0)

        bookmarks = subprocess.run(
            ["docker", "exec", c_name, "sh", "-c",
             'cat "$XDG_CONFIG_HOME/gtk-3.0/bookmarks"'],
            capture_output=True,
            text=True,
            check=False,
        )
        assert bookmarks.stdout.splitlines() == ["file:///exchange/uploads Uploads"], (
            bookmarks
        )

        page_url = f"{http_server}/file_input.html"
        exec_uds_cdp(
            c_name,
            f"""
        targets = await send_cmd(ws, 1, "Target.getTargets")
        target_id = targets["result"]["targetInfos"][0]["targetId"]
        attach = await send_cmd(
            ws, 2, "Target.attachToTarget", {{"targetId": target_id, "flatten": True}}
        )
        s = attach["result"]["sessionId"]
        await send_cmd(ws, 3, "Page.navigate", {{"url": "{page_url}"}}, session_id=s)
        await asyncio.sleep(1.0)
        await send_cmd(
            ws,
            4,
            "Runtime.evaluate",
            {{"expression": "document.getElementById('f').click()",
              "userGesture": True}},
            session_id=s,
        )
        print("RESULT:" + json.dumps({{"status": "ok"}}))
""",
        )
        names: list[str] = []
        for _ in range(20):
            names = await asyncio.to_thread(visible_window_names)
            if any(name in ("Open File", "打开文件") for name in names):
                break
            await asyncio.sleep(0.5)
        assert any(name in ("Open File", "打开文件") for name in names), names
    except Exception:
        save_container_failure_log(c_name, "p014_file_chooser")
        raise
    finally:
        stop_and_rm_container(c_name)
        if dir_work.exists():
            shutil.rmtree(dir_work, ignore_errors=True)


class _T035RecordingProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        print(f"PROXY_GET {self.path}", flush=True)
        try:
            with urllib.request.urlopen(self.path, timeout=5.0) as resp:
                body = resp.read()
            self.send_response(resp.status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:  # noqa: BLE001 - test proxy is diagnostic only
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(exc).encode())

    def log_message(self, *args: Any) -> None:
        return


@pytest.mark.asyncio
async def test_t035_proxy_outbound_and_cdp_browser_version(
    http_server: str,
) -> None:
    """t035 AC-007/008/010: a proxy configured in the frozen config snapshot
    makes browser egress traverse a local recording proxy, and the Runner
    reports CDP ``Browser.getVersion`` fields over UDS health.  The snapshot
    carries ``proxy_credential_revision`` and the mounted credentials file
    must agree, so this also exercises the fail-closed credential path."""
    if ACTIVE_TEST_NETWORK is None:
        raise RuntimeError("Docker HTTP fixture network is not initialized")
    run_id = uuid.uuid4().hex[:8]
    c_name = f"cbrowser-t035-proxy-{run_id}"
    proxy_name = f"cbrowser-t035-proxy-node-{run_id}"
    profile_id = "profile_t035_proxy"
    dir_work = SCRATCH_ROOT / f"t035_{run_id}"
    runtime_dir = dir_work / "runtime"
    profile_dir = dir_work / "profile"
    exchange = dir_work / "exchange"
    snap_file = dir_work / "snapshot.json"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    proxy_script = (
        "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "import urllib.request\n"
        + inspect.getsource(_T035RecordingProxyHandler)
        + "\nHTTPServer(('0.0.0.0', 8080), _T035RecordingProxyHandler).serve_forever()\n"
    )
    subprocess.run(
        [
            "docker", "run", "-d", "--name", proxy_name,
            "--network", ACTIVE_TEST_NETWORK,
            "--label", "cbrowser.task=t035",
            "--entrypoint", "python3", IMAGE_TAG,
            "-c", proxy_script,
        ],
        check=True, capture_output=True, text=True, timeout=30.0,
    )
    time.sleep(1.0)

    create_snapshot_file(
        snap_file, profile_id=profile_id, version=1, proxy_id="px_t035"
    )
    snapshot_payload = json.loads(snap_file.read_text(encoding="utf-8"))
    snapshot_payload["proxy_credential_revision"] = 1
    snap_file.write_text(json.dumps(snapshot_payload, indent=2), encoding="utf-8")

    creds_file = runtime_dir / "proxy_credentials.json"
    creds_file.write_text(
        json.dumps(
            {
                "scheme": "http",
                "host": proxy_name,
                "port": 8080,
                "username": None,
                "password": None,
                "credential_revision": 1,
                "proxy_credential_revision": 1,
            }
        ),
        encoding="utf-8",
    )
    os.chmod(creds_file, 0o644)

    cid = run_docker_container(
        c_name, profile_dir, runtime_dir, exchange, snap_file,
        profile_id, f"inst_t035_{run_id}",
    )
    assert cid
    try:
        health = wait_for_uds_ready(c_name)
        details = health.get("details") or {}
        assert details.get("browser_product"), (
            "AC-010: CDP Browser.getVersion product missing from UDS health"
        )
        assert details.get("browser_user_agent"), (
            "AC-010: CDP Browser.getVersion userAgent missing from UDS health"
        )

        cdp = exec_uds_cdp(
            c_name,
            f"""
            targets = await send_cmd(ws, 1, "Target.getTargets")
            pages = [t for t in targets["result"]["targetInfos"] if t["type"] == "page"]
            target_id = pages[0]["targetId"]
            attach = await send_cmd(ws, 2, "Target.attachToTarget", {{"targetId": target_id, "flatten": True}})
            s = attach["result"]["sessionId"]
            await send_cmd(ws, 3, "Page.navigate", {{"url": "{http_server}/audio_test.html?freq=440"}}, session_id=s)
            version = await send_cmd(ws, 4, "Browser.getVersion")
            await asyncio.sleep(3.0)
            print("RESULT:" + json.dumps({{"status": "ok", "product": version["result"]["product"], "userAgent": version["result"]["userAgent"]}}))
        """,
        )
        # AC-010: the runtime fields published over UDS health are exactly
        # the values the container's browser reports to CDP.
        assert details["browser_product"] == cdp["product"]
        assert details["browser_user_agent"] == cdp["userAgent"]

        deadline = time.monotonic() + 30.0
        recorded = False
        while time.monotonic() < deadline:
            logs = subprocess.run(
                ["docker", "logs", proxy_name],
                check=False, capture_output=True, text=True,
            )
            output = logs.stdout + logs.stderr
            if f"PROXY_GET {http_server}/audio_test.html" in output:
                recorded = True
                break
            await asyncio.sleep(0.5)
        assert recorded, (
            "AC-007/008: browser egress did not traverse the configured proxy"
        )
    except Exception:
        save_container_failure_log(c_name, "t035_proxy_outbound")
        raise
    finally:
        stop_and_rm_container(c_name)
        stop_and_rm_container(proxy_name)
        shutil.rmtree(dir_work, ignore_errors=True)
