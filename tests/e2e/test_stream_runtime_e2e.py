"""
Docker Real E2E Test Suite for Stream Runtime Candidate.
Verifies multi-viewer WebRTC streaming, fixed resolution 1920x1080, audio reception,
input forwarding, independent mute, and isolation with real Docker containers.
"""

import asyncio
import base64
import importlib.util
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest
from aiohttp import WSMsgType, web
from cbrowser.domain.models import ConfigVersionSnapshot, ProfileConfig
from cbrowser.stream_agent.client_shim import WEB_LOCK_SHIM_JS
from playwright.async_api import async_playwright

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BROWSER_IMAGE = os.environ.get("CBROWSER_RUNTIME_TEST_IMAGE", "")
STREAM_IMAGE = os.environ.get("CBROWSER_STREAM_TEST_IMAGE", "")
ENGINE_CACHE = os.environ.get("CBROWSER_RUNTIME_ENGINE_CACHE", "")

RUN_LABEL = "cbrowser-t004-e2e"
SCRATCH_BASE = Path(os.path.abspath(".scratch/t004_implementation/e2e_work"))


async def wait_for_viewer_count(gateway: "GatewayMockServer", expected: int,
                                timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(gateway.viewers) == expected:
            return
        await asyncio.sleep(0.1)
    raise AssertionError(
        f"Expected {expected} active viewers, got {len(gateway.viewers)}"
    )


async def wait_for_page_stats(page, stats_script: str, predicate, *,
                              timeout: float = 15.0,
                              description: str = "page stats"):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = await page.evaluate(stats_script)
        if last and predicate(last):
            return last
        await asyncio.sleep(0.1)
    raise AssertionError(f"Timed out waiting for {description}: {last}")


async def wait_for_log(log_reader, needle: str, *, offset: int = 0,
                       timeout: float = 15.0) -> str:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        last = (await log_reader())[offset:]
        if needle in last:
            return last
        await asyncio.sleep(0.2)
    raise AssertionError(f"Timed out waiting for log {needle!r}: {last[-500:]}")


class GatewayMockServer:
    """In-memory Gateway service for local E2E test fixture."""

    def __init__(
        self,
        agent_token: str,
        profile_id: str,
        stream_container: str,
        upstream_http: str = "http://127.0.0.1:18091",
    ):
        self.agent_token = agent_token
        self.profile_id = profile_id
        self.stream_container = stream_container
        self.upstream_http = upstream_http
        self.app = web.Application()
        self.registered_agents = {}  # profile_id -> (session_id, ws)
        self.agent_instances = {}
        self.control_packets = []
        self.viewers = {}  # conn_id -> (profile_id, ws)
        self.viewer_tab_ids = {}
        self.profile_viewers = {}  # profile_id -> set(conn_ids)
        self.app.router.add_get("/stream/agent/register", self.handle_agent_register)
        self.app.router.add_get(
            "/stream/{profile_id}/signal", self.handle_viewer_signal
        )
        self.app.router.add_get("/", self.static_proxy)
        self.app.router.add_get("/{path:.*}", self.static_proxy)
        self.runner = None
        self.site = None

    async def static_proxy(self, request: web.Request) -> web.Response:
        # Fixture-only asset bootstrap: the Stream HTTP listener remains loopback
        # inside its private network. Production Gateway never uses Docker exec.
        script = """import base64, json, sys, urllib.request
with urllib.request.urlopen(sys.argv[1], timeout=5) as response:
    print(json.dumps({'status':response.status, 'headers':dict(response.headers),
                      'body':base64.b64encode(response.read()).decode()}))
"""
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "docker",
                "exec",
                self.stream_container,
                "python3",
                "-c",
                script,
                self.upstream_http + request.raw_path,
            ],
            text=True,
            capture_output=True,
            timeout=8,
        )
        if result.returncode:
            return web.Response(status=502, text="Fixture asset unavailable")
        response = json.loads(result.stdout)
        body = base64.b64decode(response["body"])
        headers = response["headers"]
        for name in [
            "Transfer-Encoding",
            "Content-Encoding",
            "Connection",
            "Keep-Alive",
            "Proxy-Connection",
            "Content-Security-Policy",
        ]:
            headers.pop(name, None)
        if "text/html" in headers.get("Content-Type", ""):
            html = body.decode("utf-8")
            inject = f"""<script>
            (function() {{
                const origWS = window.WebSocket;
                window.WebSocket = function(url, protocols) {{
                    const u = new URL(url, window.location.href);
                    if (u.pathname.includes("/api/")
                        && u.pathname.includes("/signaling")) {{
                        u.pathname = "/stream/{self.profile_id}/signal";
                    }} else if (u.pathname.endsWith("/api/ws")) {{
                        u.pathname = "/stream/{self.profile_id}/signal";
                    }}
                                const ws = new origWS(u.toString(), protocols);
                    window.__last_ws = ws;
                    return ws;
                }};
                window.WebSocket.prototype = origWS.prototype;
                Object.assign(window.WebSocket, origWS);

                const origPC = window.RTCPeerConnection;
                window.RTCPeerConnection = function(...args) {{
                    const pc = new origPC(...args);
                    window.pc = pc;
                    window.__inputChannels = window.__inputChannels || [];
                    pc.addEventListener('datachannel', event => {{
                        if (event.channel.label === 'input') {{
                            window.__inputChannels.push(event.channel);
                        }}
                    }});
                    window.__pcs = window.__pcs || [];
                    window.__pcs.push(pc);
                    return pc;
                }};
                window.RTCPeerConnection.prototype = origPC.prototype;
                Object.assign(window.RTCPeerConnection, origPC);
            }})();
            </script>"""
            if "<head>" in html:
                html = html.replace("<head>", "<head>" + inject, 1)
            else:
                html = inject + html
            body = html.encode("utf-8")
        headers["Content-Length"] = str(len(body))
        return web.Response(body=body, status=response["status"], headers=headers)

    async def start(self, port: int = 18090):
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", port)
        await self.site.start()

    async def stop(self):
        # Close the fixture's live sockets before aiohttp waits for handlers.
        sockets = [entry[1] for entry in list(self.viewers.values())]
        sockets += [entry[1] for entry in list(self.registered_agents.values())]
        if sockets:
            await asyncio.gather(
                *(ws.close() for ws in sockets), return_exceptions=True
            )
        if self.runner:
            await self.runner.cleanup()

    async def handle_agent_register(
        self, request: web.Request
    ) -> web.WebSocketResponse:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {self.agent_token}":
            return web.Response(status=401, text="Unauthorized Agent")

        ws = web.WebSocketResponse()
        await ws.prepare(request)

        msg = await ws.receive()
        if msg.type != WSMsgType.TEXT:
            await ws.close()
            return ws

        reg_data = json.loads(msg.data)
        profile_id = reg_data.get("profile_id")
        assert reg_data["version"] == "v2"
        assert reg_data["action"] == "register"
        instance_id = reg_data["runtime_instance_id"]
        self.agent_instances[profile_id] = instance_id
        session_id = str(uuid.uuid4())
        self.registered_agents[profile_id] = (session_id, ws)
        self.profile_viewers[profile_id] = set()

        await ws.send_json(
            {
                "version": "v2",
                "status": "ok",
                "profile_id": profile_id,
                "runtime_instance_id": instance_id,
                "agent_session_id": session_id,
            }
        )

        try:
            async for m in ws:
                if m.type == WSMsgType.TEXT:
                    pkt = json.loads(m.data)
                    assert pkt["version"] == "v2"
                    assert pkt["profile_id"] == profile_id
                    assert pkt["runtime_instance_id"] == instance_id
                    assert pkt["agent_session_id"] == session_id
                    if pkt.get("action") in ("ice_restart_offer", "error"):
                        self.control_packets.append(pkt)
                        continue
                    conn_id = pkt.get("conn_id")
                    pkt_type = pkt.get("type")
                    if conn_id in self.viewers:
                        _, v_ws = self.viewers[conn_id]
                        if pkt_type == "msg" and not v_ws.closed:
                            await v_ws.send_str(pkt.get("data", ""))
                        elif pkt_type == "close" and not v_ws.closed:
                            await v_ws.close()
                            self.viewers.pop(conn_id, None)
                elif m.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
        finally:
            self.registered_agents.pop(profile_id, None)
        return ws

    async def handle_viewer_signal(self, request: web.Request) -> web.WebSocketResponse:
        profile_id = request.match_info.get("profile_id")
        if profile_id not in self.registered_agents:
            return web.Response(status=503, text="Profile agent offline")

        agent_session_id, agent_ws = self.registered_agents[profile_id]
        identity = {
            "version": "v2",
            "profile_id": profile_id,
            "runtime_instance_id": self.agent_instances[profile_id],
            "agent_session_id": agent_session_id,
        }
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        conn_id = str(uuid.uuid4())
        self.viewers[conn_id] = (profile_id, ws)
        self.profile_viewers[profile_id].add(conn_id)

        try:
            # Inform Agent about new viewer
            await agent_ws.send_json(
                {
                    **identity,
                    "type": "open",
                    "conn_id": conn_id,
                    "profile_id": profile_id,
                }
            )

            async for m in ws:
                if m.type == WSMsgType.TEXT:
                    if m.data.startswith("HELLO client "):
                        metadata = json.loads(m.data.split(" ", 2)[2])
                        self.viewer_tab_ids[conn_id] = metadata["client_tab_id"]
                    if not agent_ws.closed:
                        await agent_ws.send_json(
                            {
                                **identity,
                                "type": "msg",
                                "conn_id": conn_id,
                                "data": m.data,
                            }
                        )
                elif m.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
        finally:
            self.viewers.pop(conn_id, None)
            self.viewer_tab_ids.pop(conn_id, None)
            if profile_id in self.profile_viewers:
                self.profile_viewers[profile_id].discard(conn_id)
            if not agent_ws.closed:
                try:
                    await agent_ws.send_json(
                        {
                            **identity,
                            "type": "close",
                            "conn_id": conn_id,
                            "code": 1000,
                            "reason": "Viewer closed",
                        }
                    )
                except Exception:
                    pass
        return ws


def dump_container_logs(c_name: str, out_path: Path):
    res = subprocess.run(["docker", "logs", c_name], capture_output=True, text=True)
    out_path.write_text(res.stdout + "\n" + res.stderr)


def browser_eval(container: str, expression: str, target_id: str | None = None) -> dict:
    html = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "stream_probe"
        / "media_page.html"
    ).read_text()
    script = """import asyncio, json, urllib.parse, websockets


async def main():
    async with websockets.unix_connect(
        "/run/cbrowser/runtime/agent.sock", "ws://localhost/cdp"
    ) as ws:
        counter = 0

        async def command(method, params=None, session=None):
            nonlocal counter
            counter += 1
            request = {"id": counter, "method": method, "params": params or {}}
            if session:
                request["sessionId"] = session
            await ws.send(json.dumps(request))
            while True:
                result = json.loads(await asyncio.wait_for(ws.recv(), 10))
                if result.get("id") == counter:
                    if "error" in result:
                        raise RuntimeError("Browser fixture CDP request failed")
                    return result.get("result", {})

        target_id = parameters["target_id"]
        if target_id is None:
            # This fixture owns a fresh profile. Reuse its SDK-created page;
            # creating/closing targets races the SDK's own initial attachment.
            pages = [
                target
                for target in (await command("Target.getTargets"))["targetInfos"]
                if target["type"] == "page"
            ]
            if len(pages) != 1:
                raise RuntimeError("Fresh Browser fixture requires one initial page")
            target_id = pages[0]["targetId"]
        session = (
            await command(
                "Target.attachToTarget", {"targetId": target_id, "flatten": True}
            )
        )["sessionId"]
        if parameters["target_id"] is None:
            await command("Page.enable", session=session)
            await command("Runtime.enable", session=session)
            await command(
                "Page.navigate",
                {
                    "url": "data:text/html;charset=utf-8,"
                    + urllib.parse.quote(parameters["html"])
                },
                session,
            )
            for _ in range(100):
                value = await command(
                    "Runtime.evaluate",
                    {
                        "expression": '!!document.getElementById("probe_input")',
                        "returnByValue": True,
                    },
                    session,
                )
                if value.get("result", {}).get("value"):
                    break
                await asyncio.sleep(0.02)
            await command("Page.bringToFront", session=session)
        value = await command(
            "Runtime.evaluate",
            {
                "expression": parameters["expression"],
                "returnByValue": True,
                "awaitPromise": True,
                "userGesture": True,
            },
            session,
        )
        if "exceptionDetails" in value:
            raise RuntimeError("Browser fixture expression failed")
        info = json.load(open("/run/cbrowser/runtime/runner_info.json"))
        pid = info["browser_pid"]
        start_ticks = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[19]
        print(
            json.dumps(
                {
                    "target_id": target_id,
                    "identity": {"pid": pid, "start_ticks": start_ticks},
                    "value": value.get("result", {}).get("value"),
                }
            )
        )


asyncio.run(main())
"""
    script = (
        "parameters = "
        + repr({"target_id": target_id, "expression": expression, "html": html})
        + "\n"
        + script
    )
    result = subprocess.run(
        ["docker", "exec", container, "python3", "-c", script],
        text=True,
        capture_output=True,
        timeout=25,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.asyncio
async def test_stream_runtime_multi_viewer_e2e(tmp_path: Path):
    assert BROWSER_IMAGE.startswith("sha256:"), "Immutable Browser image required"
    assert STREAM_IMAGE.startswith("sha256:"), "Immutable Stream image required"
    assert Path(ENGINE_CACHE).is_dir(), "Read-only Linux engine cache required"
    """
    Validates AC-001 through AC-006:
    - Real Browser Runtime container + real Stream Runtime container.
    - Two real Google Chrome Stable pages connected over outbound Gateway bridge.
    - Frames decoded growth and audio bytesReceived growth.
    - 1920x1080 resolution invariance.
    - Closing first tab allows second tab to continue receiving media.
    """
    assert Path(CHROME_PATH).exists(), f"Google Chrome Stable required at {CHROME_PATH}"

    test_run_id = uuid.uuid4().hex[:8]
    work_dir = tmp_path / f"run_{test_run_id}"
    work_dir.mkdir(parents=True, exist_ok=True)

    net_name = f"cbrowser-t004-net-{test_run_id}"
    browser_cname = f"cbrowser-t004-browser-{test_run_id}"
    stream_cname = f"cbrowser-t004-stream-{test_run_id}"

    profile_id = f"test_p_{test_run_id}"
    agent_token = f"tok_{uuid.uuid4().hex}"
    secret_file = work_dir / "agent_secret.txt"
    secret_file.write_text(agent_token)
    selkies_cred_file = work_dir / "selkies_credentials.json"
    selkies_cred_file.write_text(
        json.dumps(
            {
                "master_token": uuid.uuid4().hex,
                "controller_token": uuid.uuid4().hex,
            }
        ),
        encoding="utf-8",
    )
    os.chmod(selkies_cred_file, 0o600)

    # Directories
    host_profile_dir = work_dir / "profile"
    host_runtime_dir = work_dir / "runtime"
    host_exchange_dir = work_dir / "downloads"
    host_events_dir = work_dir / "events"

    for d in (host_profile_dir, host_runtime_dir, host_exchange_dir, host_events_dir):
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o777)

    x11_dir = host_runtime_dir / "x11"
    pulse_dir = host_runtime_dir / "pulse"
    x11_dir.mkdir(parents=True, exist_ok=True)
    pulse_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(x11_dir, 0o777)
    os.chmod(pulse_dir, 0o777)

    # Make x11 sticky 1777 via container
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
            f"{x11_dir}:/x11",
            BROWSER_IMAGE,
            "1777",
            "/x11",
        ],
        check=True,
        timeout=15.0,
    )

    # Snapshot config
    snap_path = host_runtime_dir / "snapshot.json"
    cfg = ProfileConfig(
        screen_width=1920,
        screen_height=1080,
        geoip=False,
    )
    snapshot = ConfigVersionSnapshot(
        id=f"snap_{uuid.uuid4().hex[:12]}",
        profile_id=profile_id,
        version=1,
        config=cfg.model_dump(),
        created_at="2026-10-28T00:00:00Z",
    )
    snap_path.write_text(json.dumps(snapshot.model_dump(), indent=2))
    os.chmod(snap_path, 0o644)

    gateway = GatewayMockServer(
        agent_token=agent_token,
        profile_id=profile_id,
        stream_container=stream_cname,
        upstream_http="http://127.0.0.1:18096",
    )
    gw_port = 18097
    udp_mux_port = 30096

    created_containers = []
    clipboard_process = None
    try:
        await gateway.start(port=gw_port)

        # 1. Network setup
        subprocess.run(["docker", "network", "create", net_name], check=True)

        # 2. Start Browser Runtime
        browser_cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            browser_cname,
            "--label",
            f"{RUN_LABEL}={test_run_id}",
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
            net_name,
            "--tmpfs",
            "/tmp:rw,exec,nosuid,nodev,size=512m",
            "--tmpfs",
            "/home/cbrowser:rw,mode=0755,size=64m",
            "-v",
            f"{ENGINE_CACHE}:/data/engine-cache:ro",
            "-v",
            f"{host_profile_dir}:/data/profiles/{profile_id}/profile",
            "-v",
            f"{host_events_dir}:/data/runtime-events/{profile_id}",
            "-v",
            f"{host_exchange_dir}:/exchange/downloads",
            "-v",
            f"{host_runtime_dir}:/run/cbrowser/runtime",
            "-v",
            f"{x11_dir}:/tmp/.X11-unix",
            "-v",
            f"{pulse_dir}:/pulse",
            BROWSER_IMAGE,
            "--profile-id",
            profile_id,
            "--runtime-instance-id",
            f"inst_{test_run_id}",
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
            ":99",
        ]
        subprocess.run(browser_cmd, check=True)
        created_containers.append(browser_cname)

        # Wait for Browser sockets
        x11_socket_file = x11_dir / "X99"
        pulse_socket_file = pulse_dir / "pulse.sock"
        xauth_file = host_runtime_dir / "Xauthority"

        for _ in range(50):
            if (
                x11_socket_file.exists()
                and pulse_socket_file.exists()
                and xauth_file.exists()
            ):
                break
            await asyncio.sleep(0.2)

        assert x11_socket_file.exists(), "Browser X11 socket was not created"
        assert pulse_socket_file.exists(), "Browser PulseAudio socket was not created"
        assert xauth_file.exists(), "Browser Xauthority was not created"

        # Get Browser container hostname for Xauthority match
        b_inspect = subprocess.run(
            ["docker", "inspect", "-f", "{{.Config.Hostname}}", browser_cname],
            capture_output=True,
            text=True,
            check=True,
        )
        browser_hostname = b_inspect.stdout.strip()

        for _ in range(150):
            if (host_runtime_dir / "agent.sock").exists() and (
                host_runtime_dir / "runner_info.json"
            ).is_file():
                break
            await asyncio.sleep(0.2)
        assert (host_runtime_dir / "runner_info.json").is_file(), (
            "Runner did not become ready"
        )

        remote = await asyncio.to_thread(
            browser_eval,
            browser_cname,
            "audioContext.resume().then(() => ({state:audioContext.state, "
            "rate:audioContext.sampleRate}))",
        )
        assert remote["value"] == {"state": "running", "rate": 48000}
        target_id = remote["target_id"]

        # 3. Start Stream Runtime container
        stream_cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            stream_cname,
            "--label",
            f"{RUN_LABEL}={test_run_id}",
            "--user",
            "1000:1000",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "-h",
            browser_hostname,
            "--ipc",
            f"container:{browser_cname}",
            "--network",
            net_name,
            "-p",
            f"127.0.0.1:{udp_mux_port}:{udp_mux_port}/udp",
            "--tmpfs",
            "/tmp:rw,exec,nosuid,nodev,size=256m",
            "-v",
            f"{x11_socket_file}:/tmp/.X11-unix/X99:ro",
            "-v",
            f"{xauth_file}:/tmp/.Xauthority:ro",
            "-v",
            f"{pulse_dir}:/pulse:ro",
            "-v",
            f"{secret_file}:/tmp/secret.txt:ro",
            "-v",
            f"{selkies_cred_file}:/tmp/selkies_credentials.json:ro",
            "-e",
            "PYTHONDONTWRITEBYTECODE=1",
            "-e",
            "CBROWSER_WEBRTC_PUBLIC_IP=127.0.0.1",
            "-e",
            "DISPLAY=:99",
            "-e",
            "XAUTHORITY=/tmp/.Xauthority",
            "-e",
            f"CBROWSER_PROFILE_ID={profile_id}",
            "-e",
            f"CBROWSER_RUNTIME_INSTANCE_ID=inst_{test_run_id}",
            "-e",
            f"CBROWSER_GATEWAY_URL=ws://host.docker.internal:{gw_port}",
            "-e",
            "CBROWSER_AGENT_SECRET_FILE=/tmp/secret.txt",
            "-e",
            "CBROWSER_SELKIES_CREDENTIALS_FILE=/tmp/selkies_credentials.json",
            "-e",
            "CBROWSER_SCREEN_WIDTH=1920",
            "-e",
            "CBROWSER_SCREEN_HEIGHT=1080",
            "-e",
            f"CBROWSER_UDP_MUX_PORT={udp_mux_port}",
            "-e",
            "CBROWSER_AUDIO_DEVICE=cbrowser_sink.monitor",
            "-e",
            "CBROWSER_PULSE_DIR=/pulse",
            "-e",
            "CBROWSER_X11_SOCKET=/tmp/.X11-unix/X99",
            "-e",
            "SELKIES_PORT=18096",
            # t006 Stream startup contract: config version and the coturn
            # address reported at registration (this test sends no RTC config).
            "-e",
            "CBROWSER_CONFIG_VERSION=1",
            "-e",
            "SELKIES_TURN_HOST=127.0.0.1",
            "-e",
            "SELKIES_TURN_PORT=3478",
            STREAM_IMAGE,
        ]
        subprocess.run(stream_cmd, check=True)
        created_containers.append(stream_cname)

        # Wait for Stream Agent outbound registration with Gateway
        for _ in range(50):
            if profile_id in gateway.registered_agents:
                break
            await asyncio.sleep(0.2)

        assert profile_id in gateway.registered_agents, (
            "StreamAgent failed to register with Gateway"
        )

        stats_script = """async () => {
            const pcs = window.__pcs || window.__peerConnections || [];
            // Look for connected or active peer connection
            let pc = null;
            for (const p of pcs) {
                if (p.connectionState === 'connected'
                    || p.iceConnectionState === 'connected') {
                    pc = p;
                    break;
                }
            }
            if (!pc && pcs.length > 0) pc = pcs[pcs.length - 1];
            if (!pc) return null;

            const report = await pc.getStats();
            let inboundVideo = null;
            let inboundAudio = null;
            for (const entry of report.values()) {
                if (entry.type === 'inbound-rtp') {
                    if (entry.kind === 'video') inboundVideo = entry;
                    if (entry.kind === 'audio') inboundAudio = entry;
                }
            }
            const transport = [...report.values()].find(
                entry => entry.type === 'transport' && entry.selectedCandidatePairId
            );
            const pair = transport && report.get(transport.selectedCandidatePairId);
            const remoteCandidate = pair && report.get(pair.remoteCandidateId);
            return {
                selectedRemoteCandidate: remoteCandidate ? {
                    address: remoteCandidate.address,
                    port: remoteCandidate.port,
                    protocol: remoteCandidate.protocol,
                    candidateType: remoteCandidate.candidateType
                } : null,
                connectionState: pc.connectionState,
                iceConnectionState: pc.iceConnectionState,
                video: inboundVideo ? {
                    framesDecoded: inboundVideo.framesDecoded || 0,
                    keyFramesDecoded: inboundVideo.keyFramesDecoded || 0,
                    bytesReceived: inboundVideo.bytesReceived || 0,
                    frameWidth: inboundVideo.frameWidth || 0,
                    frameHeight: inboundVideo.frameHeight || 0
                } : null,
                audio: inboundAudio ? {
                    bytesReceived: inboundAudio.bytesReceived || 0,
                    totalAudioEnergy: inboundAudio.totalAudioEnergy || 0
                } : null
            };
        }"""

        # 4. Launch official Google Chrome Stable with Playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                executable_path=CHROME_PATH,
                headless=True,
                args=[
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-gpu",
                    "--autoplay-policy=no-user-gesture-required",
                ],
            )
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            await context.add_init_script(WEB_LOCK_SHIM_JS)
            await context.add_init_script("""(() => {
                window.__nativeComposition = [];
                window.__nativeCommits = [];
                for (const type of ['compositionstart','compositionupdate',
                                    'compositionend','input','textInput']) {
                    document.addEventListener(type, event => {
                        window.__nativeComposition.push({
                            type, trusted:event.isTrusted, target:event.target.id
                        });
                    }, true);
                }
                const nativeSend = RTCDataChannel.prototype.send;
                RTCDataChannel.prototype.send = function(data) {
                    if (typeof data === 'string' && data.startsWith('co,end,')) {
                        window.__nativeCommits.push(data);
                    }
                    return nativeSend.call(this, data);
                };
            })();""")

            # Tab 1
            await context.add_init_script("""(() => {
                window.__initialCopiedTabId = sessionStorage.getItem('selkies_tab_id');
            })();""")
            page1 = await context.new_page()
            await page1.goto(f"http://127.0.0.1:{gw_port}/#primary", wait_until="load")

            # Tab 2
            page2 = await context.new_page()
            await page2.goto(f"http://127.0.0.1:{gw_port}/#primary", wait_until="load")

            # Check both viewers connected
            await wait_for_viewer_count(gateway, 2)

            # Wait for WebRTC media decoding on Tab 1 and Tab 2
            stats1 = None
            stats2 = None
            for _ in range(30):
                await asyncio.sleep(1.0)
                stats1 = await page1.evaluate(stats_script)
                stats2 = await page2.evaluate(stats_script)
                if stats1 and stats1.get("video") and stats2 and stats2.get("video"):
                    if (
                        stats1["video"]["framesDecoded"] > 0
                        and stats2["video"]["framesDecoded"] > 0
                    ):
                        break

            assert stats1 and stats1.get("video"), "Tab 1 video stats missing"
            assert stats2 and stats2.get("video"), "Tab 2 video stats missing"
            assert stats1["video"]["frameWidth"] == 1920, (
                f"Expected width 1920, got {stats1['video']['frameWidth']}"
            )
            assert stats1["video"]["frameHeight"] == 1080, (
                f"Expected height 1080, got {stats1['video']['frameHeight']}"
            )
            assert stats2["video"]["frameWidth"] == 1920, (
                f"Expected width 1920, got {stats2['video']['frameWidth']}"
            )
            assert stats2["video"]["frameHeight"] == 1080, (
                f"Expected height 1080, got {stats2['video']['frameHeight']}"
            )

            # Test audio transmission: request START_AUDIO on both tabs
            for page in (page1, page2):
                await page.evaluate("""() => window.postMessage({
                    type:'pipelineControl', pipeline:'audio', enabled:true
                }, location.origin)""")
            for _ in range(50):
                stats1 = await page1.evaluate(stats_script)
                stats2 = await page2.evaluate(stats_script)
                if all(
                    st and st.get("audio") and st["audio"]["totalAudioEnergy"] > 0
                    for st in (stats1, stats2)
                ):
                    break
                await asyncio.sleep(0.1)
            assert all(
                st and st.get("audio") and st["audio"]["totalAudioEnergy"] > 0
                for st in (stats1, stats2)
            ), "Actual non-silent audio missing"

            # Check audio and video growth
            frames1_initial = stats1["video"]["framesDecoded"]
            frames2_initial = stats2["video"]["framesDecoded"]

            def _media_grew(stats, initial) -> bool:
                return (
                    stats["video"]["framesDecoded"]
                    > initial["video"]["framesDecoded"]
                    and stats["audio"]["bytesReceived"]
                    > initial["audio"]["bytesReceived"]
                    and stats["audio"]["totalAudioEnergy"]
                    > initial["audio"]["totalAudioEnergy"]
                )

            stats1_later = await wait_for_page_stats(
                page1,
                stats_script,
                lambda st: _media_grew(st, stats1),
                description="Tab 1 media growth",
            )
            stats2_later = await wait_for_page_stats(
                page2,
                stats_script,
                lambda st: _media_grew(st, stats2),
                description="Tab 2 media growth",
            )

            for stats in (stats1_later, stats2_later):
                candidate = stats["selectedRemoteCandidate"]
                assert candidate["port"] == udp_mux_port
                assert candidate["protocol"] == "udp"
                assert candidate["address"] == "127.0.0.1"
            assert stats1_later["video"]["framesDecoded"] > frames1_initial, (
                "Tab 1 frames not decoded"
            )
            assert stats2_later["video"]["framesDecoded"] > frames2_initial, (
                "Tab 2 frames not decoded"
            )

            for initial, later in ((stats1, stats1_later), (stats2, stats2_later)):
                assert (
                    later["audio"]["bytesReceived"] > initial["audio"]["bytesReceived"]
                )
                assert (
                    later["audio"]["totalAudioEnergy"]
                    > initial["audio"]["totalAudioEnergy"]
                )

            inspections = json.loads(
                subprocess.check_output(
                    ["docker", "inspect", browser_cname, stream_cname], text=True
                )
            )
            browser_inspect, stream_inspect = inspections
            host_config = stream_inspect["HostConfig"]
            assert host_config["NetworkMode"] == net_name
            assert host_config["IpcMode"] == "container:" + browser_inspect["Id"]
            assert not host_config["PidMode"] and host_config["ReadonlyRootfs"]
            assert not host_config["Privileged"] and "ALL" in host_config["CapDrop"]
            assert stream_inspect["Config"]["User"] == "1000:1000"
            mount_targets = {mount["Destination"] for mount in stream_inspect["Mounts"]}
            assert mount_targets == {
                "/tmp/.X11-unix/X99",
                "/tmp/.Xauthority",
                "/pulse",
                "/tmp/secret.txt",
            }
            (work_dir / "active_media_phase.json").write_text(
                json.dumps(
                    {
                        "initial": [stats1, stats2],
                        "later": [stats1_later, stats2_later],
                        "stream_network": host_config["NetworkMode"],
                        "stream_ipc": host_config["IpcMode"],
                        "stream_mount_targets": sorted(mount_targets),
                    },
                    indent=2,
                )
            )

            # AC002 Duplicate Tab Media Verification
            # Record initial page1/page2 stats, connection state, and PC references
            p1_tab_id_before = await page1.evaluate(
                "sessionStorage.getItem('selkies_tab_id')"
            )
            p2_tab_id_before = await page2.evaluate(
                "sessionStorage.getItem('selkies_tab_id')"
            )
            await page1.evaluate("""() => {
                window.__origConnectedPC = (window.__pcs || []).find(
                    p => p.connectionState === 'connected');
                window.__origPcsLen = (window.__pcs || []).length;
            }""")
            await page2.evaluate("""() => {
                window.__origConnectedPC = (window.__pcs || []).find(
                    p => p.connectionState === 'connected');
                window.__origPcsLen = (window.__pcs || []).length;
            }""")
            stats1_pre_dup = await page1.evaluate(stats_script)
            stats2_pre_dup = await page2.evaluate(stats_script)

            # window.open clones sessionStorage through its native opener.
            async with context.expect_page() as page_info:
                await page1.evaluate("window.open(location.href, '_blank')")
            page3 = await page_info.value
            await page3.wait_for_load_state("load")

            # Check if window.open cloned sessionStorage
            init_copied_tab_id = await page3.evaluate("window.__initialCopiedTabId")
            assert init_copied_tab_id == p1_tab_id_before, (
                f"Expected copied ID {p1_tab_id_before}, got {init_copied_tab_id}"
            )

            # Wait for third page to connect and decode media
            stats3 = None
            for _ in range(30):
                await asyncio.sleep(1.0)
                stats3 = await page3.evaluate(stats_script)
                if (
                    stats3
                    and stats3.get("video")
                    and stats3["video"]["framesDecoded"] > 0
                ):
                    break

            assert stats3 and stats3.get("video"), "Tab 3 video stats missing"
            assert stats3["video"]["framesDecoded"] > 0, "Tab 3 frames not decoded"
            assert (stats3["video"]["frameWidth"], stats3["video"]["frameHeight"]) == (
                1920,
                1080,
            ), f"Tab 3 geometry unexpected: {stats3['video']}"

            # Verify Tab 3 has remapped ID different from Tab 1 and Tab 2
            p3_tab_id_after = await page3.evaluate(
                "sessionStorage.getItem('selkies_tab_id')"
            )
            assert p3_tab_id_after != p1_tab_id_before, (
                f"Tab 3 selkies_tab_id not remapped: {p3_tab_id_after}"
            )
            assert p3_tab_id_after != p2_tab_id_before, (
                f"Tab 3 collided with Tab 2: {p3_tab_id_after}"
            )
            assert len(gateway.viewers) == 3, (
                f"Expected 3 active viewers, got {len(gateway.viewers)}"
            )

            # Original peers retain their connections and keep playing.
            stats1_post_dup = await wait_for_page_stats(
                page1,
                stats_script,
                lambda st: (
                    st["video"]["framesDecoded"]
                    > stats1_pre_dup["video"]["framesDecoded"]
                    and st["audio"]["totalAudioEnergy"]
                    > stats1_pre_dup["audio"]["totalAudioEnergy"]
                ),
                description="Page 1 media growth after duplicate tab",
            )
            stats2_post_dup = await wait_for_page_stats(
                page2,
                stats_script,
                lambda st: (
                    st["video"]["framesDecoded"]
                    > stats2_pre_dup["video"]["framesDecoded"]
                    and st["audio"]["totalAudioEnergy"]
                    > stats2_pre_dup["audio"]["totalAudioEnergy"]
                ),
                description="Page 2 media growth after duplicate tab",
            )
            assert (
                stats1_post_dup["video"]["framesDecoded"]
                > stats1_pre_dup["video"]["framesDecoded"]
            ), "Page 1 frames did not grow during duplicate tab phase"
            assert (
                stats2_post_dup["video"]["framesDecoded"]
                > stats2_pre_dup["video"]["framesDecoded"]
            ), "Page 2 frames did not grow during duplicate tab phase"
            assert (
                stats1_post_dup["audio"]["totalAudioEnergy"]
                > stats1_pre_dup["audio"]["totalAudioEnergy"]
            ), "Page 1 audio did not grow"
            assert (
                stats2_post_dup["audio"]["totalAudioEnergy"]
                > stats2_pre_dup["audio"]["totalAudioEnergy"]
            ), "Page 2 audio did not grow"

            for page in (page1, page2):
                pc_check = await page.evaluate("""() => ({
                    pcsLen: (window.__pcs || []).length,
                    origLen: window.__origPcsLen,
                    connectedPC: (window.__pcs || []).find(
                    p => p.connectionState === 'connected') ===
                        window.__origConnectedPC
                })""")
                assert pc_check["pcsLen"] == pc_check["origLen"], (
                    f"__pcs length increased on original page: {pc_check}"
                )
                assert pc_check["connectedPC"], (
                    f"Original connected PC was replaced: {pc_check}"
                )

            # Closing the clone preserves both original viewers.
            await page3.close()
            for _ in range(20):
                if len(gateway.viewers) == 2:
                    break
                await asyncio.sleep(0.2)
            assert len(gateway.viewers) == 2, (
                f"Expected 2 viewers after closing Tab 3, got {len(gateway.viewers)}"
            )

            stats1_after_close = await page1.evaluate(stats_script)
            stats2_after_close = await page2.evaluate(stats_script)
            assert (
                stats1_after_close["video"]["framesDecoded"]
                > stats1_post_dup["video"]["framesDecoded"]
            ), "Page 1 media stalled after Tab 3 closed"
            assert (
                stats2_after_close["video"]["framesDecoded"]
                > stats2_post_dup["video"]["framesDecoded"]
            ), "Page 2 media stalled after Tab 3 closed"

            (work_dir / "duplicate_tab_media_proof.json").write_text(
                json.dumps(
                    {
                        "p1_tab_id_before": p1_tab_id_before,
                        "init_copied_tab_id": init_copied_tab_id,
                        "p3_tab_id_after": p3_tab_id_after,
                        "storage_adapted": False,
                        "tab3_video": stats3["video"],
                        "viewers_during_tab3": 3,
                        "viewers_after_close": len(gateway.viewers),
                    },
                    indent=2,
                )
            )

            relay_spec = importlib.util.spec_from_file_location(
                "chrome_relay",
                Path(__file__).resolve().parents[1]
                / "fixtures/stream_probe/chrome_relay.py",
            )
            relay_module = importlib.util.module_from_spec(relay_spec)
            relay_spec.loader.exec_module(relay_module)
            await relay_module.verify_relay_rotations(
                page1,
                page2,
                gateway,
                profile_id,
                net_name,
                stream_cname,
                work_dir,
                created_containers,
                stats_script,
            )

            async def evaluate_remote(expression):
                return await asyncio.to_thread(
                    browser_eval, browser_cname, expression, target_id
                )

            async def policy_packet(action, payload):
                agent_session_id, agent_socket = gateway.registered_agents[profile_id]
                await agent_socket.send_json(
                    {
                        "version": "v2",
                        "action": action,
                        "profile_id": profile_id,
                        "runtime_instance_id": gateway.agent_instances[profile_id],
                        "agent_session_id": agent_session_id,
                        "payload": payload,
                    }
                )

            async def native_logs():
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["docker", "logs", stream_cname],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=True,
                    timeout=10,
                )
                return result.stdout

            async def frame_window(page=page1, seconds=2):
                before = await page.evaluate(stats_script)
                await asyncio.sleep(seconds)
                after = await page.evaluate(stats_script)
                return (
                    after["video"]["framesDecoded"] - before["video"]["framesDecoded"]
                )

            control_proof = {}
            for page in (page1, page2):
                await page.wait_for_function("""() => window.__inputChannels &&
                    window.__inputChannels.some(
                        channel => channel.readyState === 'open')
                """)
            tab1 = await page1.evaluate("sessionStorage.getItem('selkies_tab_id')")
            tab2 = await page2.evaluate("sessionStorage.getItem('selkies_tab_id')")
            by_tab = {
                tab: connection for connection, tab in gateway.viewer_tab_ids.items()
            }
            assert tab1 != tab2 and tab1 in by_tab and tab2 in by_tab
            before_cap_logs = await native_logs()
            await policy_packet("supervisor_quota", {"max_fps_cap": 15})
            await wait_for_log(
                native_logs,
                "Updated framerate to 15 fps",
                offset=len(before_cap_logs),
            )
            control_proof["capped_frames_2s"] = await frame_window()
            assert 0 < control_proof["capped_frames_2s"] <= 40
            # Client input must not override Supervisor cap or profile geometry.
            await page1.evaluate("""() => {
                const channel = window.__inputChannels.find(
                    c => c.readyState === 'open');
                channel.send('_arg_fps,30');
                channel.send('r,640,480');
            }""")
            await asyncio.sleep(0.5)
            control_proof["client_cannot_escape_cap_frames_2s"] = await frame_window()
            assert 0 < control_proof["client_cannot_escape_cap_frames_2s"] <= 40
            await page1.set_viewport_size({"width": 640, "height": 480})
            await page2.set_viewport_size({"width": 1600, "height": 900})
            await asyncio.sleep(0.5)
            for page in (page1, page2):
                geometry = (await page.evaluate(stats_script))["video"]
                assert (geometry["frameWidth"], geometry["frameHeight"]) == (1920, 1080)
            await policy_packet("supervisor_quota", {"max_fps_cap": None})
            await wait_for_log(
                native_logs,
                "Updated framerate to 30 fps",
                offset=len(before_cap_logs),
            )
            control_proof["restored_frames_2s"] = await frame_window()
            assert control_proof["restored_frames_2s"] > 0

            before_static_logs = await native_logs()
            await evaluate_remote("motionEnabled=false; true")
            await wait_for_log(
                native_logs,
                "Updated framerate to 8 fps",
                offset=len(before_static_logs),
            )
            await evaluate_remote("motionEnabled=true; true")
            await wait_for_log(
                native_logs,
                "Updated framerate to 30 fps",
                offset=len(before_static_logs),
            )

            resource_spec = importlib.util.spec_from_file_location(
                "supervisor_stream_monitor",
                Path(__file__).resolve().parents[1]
                / "fixtures/supervisor_resource_probe/stream_monitor.py",
            )
            resource_module = importlib.util.module_from_spec(resource_spec)
            resource_spec.loader.exec_module(resource_module)
            await resource_module.verify_stream_cpu_policy(
                stream_cname,
                profile_id,
                gateway,
                frame_window,
                work_dir,
            )

            after_policy = await evaluate_remote("true")
            assert after_policy["identity"] == remote["identity"]
            control_proof["browser_identity"] = after_policy["identity"]
            (work_dir / "policy_proof.json").write_text(
                json.dumps(control_proof, indent=2)
            )
            (work_dir / "native_policy.log").write_text(await native_logs())

            async def prepare_remote_input():
                await evaluate_remote("""(() => {
                    const input=document.getElementById('probe_input');
                    input.value=''; window.remoteEvents=[]; input.focus(); return true;
                })()""")

            async def remote_value():
                return (
                    await evaluate_remote(
                        "document.getElementById('probe_input').value"
                    )
                )["value"]

            await prepare_remote_input()
            await page1.bring_to_front()
            await page1.locator("#overlayInput").focus()
            await page1.keyboard.press("Digit1")
            for _ in range(20):
                if await remote_value() == "1":
                    break
                await asyncio.sleep(0.1)
            (work_dir / "ascii_attempt.json").write_text(
                json.dumps(
                    (
                        await evaluate_remote(
                            "({value:document.getElementById('probe_input').value, "
                            "focused:document.hasFocus(), "
                            "active:document.activeElement.id, "
                            "events:window.remoteEvents})"
                        )
                    )["value"],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            assert await remote_value() == "1", (
                "First-page-only negative control failed"
            )
            await prepare_remote_input()
            await page1.bring_to_front()
            await page1.locator("#overlayInput").focus()
            await page1.keyboard.press("Digit1")
            await page2.bring_to_front()
            await page2.locator("#overlayInput").focus()
            await page2.keyboard.press("Digit2")
            for _ in range(20):
                if await remote_value() == "12":
                    break
                await asyncio.sleep(0.1)
            assert await remote_value() == "12", (
                "Both pages must reach the same browser"
            )

            clipboard_script = (
                Path(__file__).resolve().parents[1]
                / "fixtures"
                / "stream_probe"
                / "clipboard_oracle.py"
            ).read_text()
            clipboard_process = subprocess.Popen(
                [
                    "docker",
                    "exec",
                    "-i",
                    stream_cname,
                    "python3",
                    "-u",
                    "-c",
                    clipboard_script,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            async def clipboard_line(prefix):
                async with asyncio.timeout(10):
                    while True:
                        line = await asyncio.to_thread(
                            clipboard_process.stdout.readline
                        )
                        assert line, "Native clipboard oracle exited before replying"
                        if line.startswith(prefix):
                            return line.strip().removeprefix(prefix)

            await clipboard_line("CBR_CLIP_READY")
            ime_proofs = []
            ime_cases = [(page1, "zhongwen", "中文"), (page2, "shuru", "输入")]
            # Distinct commits exercise native spare-key reuse after an active map.
            ime_cases.extend(
                (
                    page1 if index % 2 == 0 else page2,
                    "ceshi",
                    "".join(chr(0x4E00 + index * 20 + offset) for offset in range(20)),
                )
                for index in range(6)
            )
            for page, composition, text in ime_cases:
                await prepare_remote_input()
                await page.bring_to_front()
                await page.locator("#overlayInput").focus()
                await page.wait_for_function(
                    "document.hasFocus() && "
                    "document.activeElement.id === 'overlayInput'"
                )
                external_cdp = await context.new_cdp_session(page)
                await external_cdp.send(
                    "Input.imeSetComposition",
                    {
                        "text": composition,
                        "selectionStart": len(composition),
                        "selectionEnd": len(composition),
                    },
                )
                await asyncio.sleep(0.2)
                await external_cdp.send("Input.insertText", {"text": text})
                for _ in range(20):
                    if await remote_value() == text:
                        break
                    await asyncio.sleep(0.1)
                observed = await remote_value()
                diagnostic = await page.evaluate("""() => ({
                    focused: document.hasFocus(), active:document.activeElement.id,
                    events:window.__nativeComposition, commits:window.__nativeCommits
                })""")
                diagnostic["remote_value"] = observed
                diagnostic["remote_state"] = (
                    await evaluate_remote("""({
                    focused:document.hasFocus(),active:document.activeElement.id,
                    events:window.remoteEvents
                })""")
                )["value"]
                (work_dir / f"ime_attempt_{len(ime_proofs)}.json").write_text(
                    json.dumps(diagnostic, ensure_ascii=False, indent=2)
                )
                assert observed == text, "Native composition missed the remote DOM"
                events = await page.evaluate("window.__nativeComposition")
                commits = await page.evaluate("window.__nativeCommits")
                assert any(
                    e["type"] == "compositionstart" and e["trusted"] for e in events
                )
                assert "co,end," + text in commits
                ime_proofs.append(
                    {"trusted_composition": True, "native_channel_commit": True}
                )
                await external_cdp.detach()
            clipboard_process.stdin.write("verify\n")
            clipboard_process.stdin.flush()
            clipboard_proof = json.loads(await clipboard_line("CBR_CLIP_RESULT:"))
            assert clipboard_proof["unchanged"], (
                "Chinese composition changed X11 clipboard"
            )

            tab_id = await page1.evaluate("sessionStorage.getItem('selkies_tab_id')")
            await page2.evaluate("""() => {
                window.__survivorPC = window.__pcs.find(
                    peer => peer.connectionState === 'connected'
                );
                window.__survivorPeerCount = window.__pcs.length;
            }""")
            before_refresh = await page2.evaluate(stats_script)
            await page1.reload(wait_until="load")
            assert (
                await page1.evaluate("sessionStorage.getItem('selkies_tab_id')")
                == tab_id
            )
            for _ in range(100):
                refreshed = await page1.evaluate(stats_script)
                if (
                    refreshed
                    and refreshed.get("video")
                    and refreshed["video"]["framesDecoded"] > 0
                ):
                    break
                await asyncio.sleep(0.1)
            assert (
                refreshed
                and refreshed.get("video")
                and refreshed["video"]["framesDecoded"] > 0
            )
            assert await page2.evaluate("""() =>
                window.__pcs.length === window.__survivorPeerCount &&
                window.__pcs.find(peer => peer.connectionState === 'connected')
                    === window.__survivorPC
            """)
            after_refresh = await page2.evaluate(stats_script)
            assert (
                after_refresh["video"]["framesDecoded"]
                > before_refresh["video"]["framesDecoded"]
            )
            assert (
                after_refresh["audio"]["totalAudioEnergy"]
                > before_refresh["audio"]["totalAudioEnergy"]
            )
            for page in (page1, page2):
                await page.evaluate("""() => window.postMessage({
                    type:'pipelineControl', pipeline:'audio', enabled:true
                }, location.origin)""")

            # Mute Tab 1 while Tab 2 continues receiving media.
            await page1.evaluate("""() => window.postMessage({
                type:'pipelineControl', pipeline:'audio', enabled:false
            }, location.origin)""")
            await page1.wait_for_function("document.querySelector('video').muted")
            await asyncio.sleep(1.0)

            # Close Tab 1, ensure Tab 2 remains active and continues receiving media
            await page1.close()
            await wait_for_viewer_count(gateway, 1)
            stats2_after_close = await wait_for_page_stats(
                page2,
                stats_script,
                lambda st: (
                    st["video"]["framesDecoded"]
                    > stats2_later["video"]["framesDecoded"]
                    and st["audio"]["totalAudioEnergy"]
                    > stats2_later["audio"]["totalAudioEnergy"]
                ),
                description="Tab 2 media growth after closing Tab 1",
            )
            assert stats2_after_close["connectionState"] == "connected", (
                "Tab 2 dropped connection"
            )
            assert (
                stats2_after_close["video"]["framesDecoded"]
                > stats2_later["video"]["framesDecoded"]
            )
            assert (
                stats2_after_close["audio"]["totalAudioEnergy"]
                > stats2_later["audio"]["totalAudioEnergy"]
            )
            final_browser = await evaluate_remote("true")
            assert final_browser["identity"] == remote["identity"], (
                "Browser process restarted"
            )
            await prepare_remote_input()
            await page2.bring_to_front()
            await page2.locator("#overlayInput").focus()
            await page2.keyboard.press("Digit3")
            for _ in range(20):
                if await remote_value() == "3":
                    break
                await asyncio.sleep(0.1)
            assert await remote_value() == "3", "Surviving page lost input"

            # The agent must re-register without restarting its Browser donor.
            before_disconnect = await evaluate_remote("index")
            old_session, agent_socket = gateway.registered_agents[profile_id]
            await agent_socket.close()
            reconnected = None
            for _ in range(100):
                current = gateway.registered_agents.get(profile_id)
                if current and current[0] != old_session:
                    reconnected = current[0]
                    break
                await asyncio.sleep(0.1)
            assert reconnected, "Stream Agent did not re-register after disconnect"
            after_disconnect = await evaluate_remote("index")
            assert after_disconnect["identity"] == remote["identity"]
            assert after_disconnect["value"] > before_disconnect["value"]

            # Freeze only this test's owned media container. The donor must
            # continue running its browser and animation in a separate sandbox.
            before_pause = await evaluate_remote("index")
            await asyncio.to_thread(
                subprocess.run,
                ["docker", "pause", stream_cname],
                check=True,
                capture_output=True,
                timeout=10,
            )
            try:
                await asyncio.sleep(0.3)
                during_pause = await evaluate_remote("index")
                assert during_pause["identity"] == remote["identity"]
                assert during_pause["value"] > before_pause["value"]
            finally:
                await asyncio.to_thread(
                    subprocess.run,
                    ["docker", "unpause", stream_cname],
                    check=True,
                    capture_output=True,
                    timeout=10,
                )
            isolation_proof = {
                "agent_reconnected": True,
                "browser_advanced_during_disconnect": True,
                "browser_advanced_during_stream_pause": True,
                "browser_identity": during_pause["identity"],
            }
            (work_dir / "media_proof.json").write_text(
                json.dumps(
                    {
                        "native_ime": ime_proofs,
                        "capture_policy": control_proof,
                        "isolation": isolation_proof,
                        "clipboard": clipboard_proof,
                        "browser_identity": final_browser["identity"],
                        "refresh_survived": True,
                        "initial": [stats1, stats2],
                        "later": [stats1_later, stats2_later],
                        "after_first_closed": stats2_after_close,
                        "remote_fixture": remote,
                    },
                    indent=2,
                )
            )

            await browser.close()

    except Exception as e:
        # Save docker logs on error
        for cname in created_containers:
            dump_container_logs(cname, work_dir / f"{cname}.log")
        raise e
    finally:
        if clipboard_process is not None:
            if clipboard_process.poll() is None:
                try:
                    clipboard_process.stdin.write("close\n")
                    clipboard_process.stdin.flush()
                    await asyncio.to_thread(clipboard_process.wait, 5)
                except (OSError, subprocess.TimeoutExpired):
                    clipboard_process.terminate()
            for pipe in (
                clipboard_process.stdin,
                clipboard_process.stdout,
                clipboard_process.stderr,
            ):
                if pipe:
                    pipe.close()
        await gateway.stop()
        for cname in created_containers:
            subprocess.run(
                ["docker", "rm", "-f", cname],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        subprocess.run(
            ["docker", "network", "rm", net_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
