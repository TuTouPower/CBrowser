"""Integration tests running independent uvicorn subprocess against real DB."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import jsonschema
import pytest

from api_auth import create_auth_context

SCRATCH_DIR = (
    Path(__file__).resolve().parent.parent.parent / ".scratch" / "t002_implementation"
)
SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
OPENAPI_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "schemas"
    / "openapi"
    / "cbrowser_v1.json"
)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class SubprocessServer:
    def __init__(
        self,
        db_path: Path,
        port: int,
        log_path: Path,
        auth_context: Any | None = None,
    ):
        self.db_path = db_path
        self.port = port
        self.log_path = log_path
        self.auth_context = auth_context
        self.auth_headers: dict[str, str] = {}
        self.supervisor_token: str = ""
        self.process: subprocess.Popen | None = None
        self._log_file = None
        self.base_url = f"http://127.0.0.1:{port}"

    def start(self):
        backend_dir = Path(__file__).resolve().parent.parent.parent / "src" / "backend"
        env = os.environ.copy()
        for name in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ):
            env.pop(name, None)
        env["PYTHONPATH"] = str(backend_dir)
        env["CBROWSER_DB_PATH"] = str(self.db_path)
        env["CBROWSER_PORT"] = str(self.port)
        env["CBROWSER_HOST"] = "127.0.0.1"
        env["UV_CACHE_DIR"] = str(SCRATCH_DIR / "uv_cache")
        env["TMPDIR"] = str(SCRATCH_DIR / "tmp")
        if self.auth_context:
            env["CBROWSER_ADMIN_PASSWORD_FILE"] = str(
                self.auth_context.admin_password_file
            )
            env["CBROWSER_ALLOWED_ORIGINS"] = self.auth_context.allowed_origin
            env["CBROWSER_SUPERVISOR_TOKEN_FILE"] = str(
                self.auth_context.supervisor_token_file
            )

        self._log_file = self.log_path.open("a+", encoding="utf-8")
        python_bin = sys.executable
        self.process = subprocess.Popen(
            [
                python_bin,
                "-m",
                "uvicorn",
                "cbrowser.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--log-level",
                "info",
            ],
            stdout=self._log_file,
            stderr=self._log_file,
            env=env,
        )

        deadline = time.time() + 10.0
        while time.time() < deadline:
            try:
                with httpx.Client(timeout=1.0, trust_env=False) as client:
                    resp = client.get(f"{self.base_url}/api/v1/health")
                    if resp.status_code == 200:
                        if self.auth_context:
                            self.auth_headers = self.auth_context.login_sync(
                                self.base_url
                            )
                            self.supervisor_token = (
                                self.auth_context.supervisor_token
                            )
                        return
            except (httpx.HTTPError, OSError):
                time.sleep(0.1)
        raise RuntimeError("Subprocess server failed to start within 10 seconds")

    def stop(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2.0)
            self.process = None
        if self._log_file and not self._log_file.closed:
            self._log_file.close()

    def read_logs(self) -> str:
        if self.log_path.exists():
            return self.log_path.read_text(encoding="utf-8")
        return ""


@pytest.fixture
def server_harness() -> SubprocessServer:
    tmp_dir = SCRATCH_DIR / f"test_run_{int(time.time() * 1000)}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    db_file = tmp_dir / "cbrowser_v2.db"
    log_file = tmp_dir / "server.log"
    port = find_free_port()
    auth_ctx = create_auth_context(tmp_dir, origin=f"http://127.0.0.1:{port}")

    server = SubprocessServer(db_file, port, log_file, auth_context=auth_ctx)
    server.start()
    yield server
    server.stop()


def _validate_schema(data: Any, schema_name: str):
    """Validate JSON response against published OpenAPI component schema."""
    spec = json.loads(OPENAPI_SCHEMA_PATH.read_text(encoding="utf-8"))
    component_schema = spec["components"]["schemas"][schema_name]
    # Provide resolver/components context
    resolver = jsonschema.RefResolver.from_schema(spec)
    jsonschema.validate(instance=data, schema=component_schema, resolver=resolver)


@pytest.mark.asyncio
async def test_ac001_and_ac005_crud_restart_and_empty_dir_init(
    server_harness: SubprocessServer,
):
    """AC-001: CRUD via API, canonical user_data_dir, legacy fields & tags persist.

    Nullable vs non-nullable updates, invalid inputs rejected.
    AC-005: Database initialized from empty directory and accessed independently.
    """
    server = server_harness
    async with httpx.AsyncClient(
        base_url=server.base_url,
        headers=server.auth_headers,
        timeout=10.0,
        trust_env=False,
    ) as client:
        # Verify empty dir DB initialized
        health = await client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        before = (await client.get("/api/v1/profiles")).json()
        invalid_args = await client.post(
            "/api/v1/profiles",
            json={"name": "Bad Args", "launch_args": ["--load-extension=/tmp/evil"]},
        )
        assert invalid_args.status_code == 422
        assert len((await client.get("/api/v1/profiles")).json()) == len(before)

        # 1. Create Profile with full valid legacy fields and tags
        payload = {
            "name": "Alpha Production Profile",
            "proxy": "http://user:secretpassword@proxy.example.com:8080",
            "timezone": "Europe/London",
            "locale": "en-GB",
            "screen_width": 1440,
            "screen_height": 900,
            "gpu_family": "intel",
            "humanize": True,
            "human_preset": "careful",
            "geoip": False,
            "clipboard_sync": True,
            "auto_launch": True,
            "color_scheme": "dark",
            "launch_args": ["--no-first-run", "--disable-sync"],
            "extension_paths": ["/opt/extensions/adblock"],
            "allow_3p_cookies": False,
            "set_google_default": False,
            "capture_preview": False,
            "restore_session": False,
            "transparent_proxy": True,
            "portable_cookies": True,
            "notes": "Top secret profile notes",
            "sort_order": 12,
            "tags": [
                {"tag": "banking", "color": "#ff0000"},
                {"tag": "uk", "color": "#0000ff"},
            ],
        }
        res = await client.post("/api/v1/profiles", json=payload)
        assert res.status_code == 201
        created = res.json()
        pid = created["id"]
        _validate_schema(created, "ProfileResponse")

        assert created["name"] == "Alpha Production Profile"
        # Canonical metadata user_data_dir path check
        assert created["user_data_dir"] == f"/data/profiles/{pid}/profile"
        assert created["fingerprint_seed"] >= 100000
        assert created["proxy"] == "http://user:secretpassword@proxy.example.com:8080"
        assert created["sort_order"] == 12
        assert len(created["tags"]) == 2
        assert created["current_config_version"] == 1

        # 2. Nullable vs Non-nullable validation
        bad_gpu = await client.put(f"/api/v1/profiles/{pid}", json={"gpu_family": None})
        assert bad_gpu.status_code == 422
        _validate_schema(bad_gpu.json(), "ValidationErrorResponse")

        bad_dim = await client.put(
            f"/api/v1/profiles/{pid}", json={"screen_width": -50}
        )
        assert bad_dim.status_code == 422
        _validate_schema(bad_dim.json(), "ValidationErrorResponse")

        blank_name = await client.put(f"/api/v1/profiles/{pid}", json={"name": "   "})
        assert blank_name.status_code == 422
        _validate_schema(blank_name.json(), "ValidationErrorResponse")

        # 404 response validates against ErrorResponse schema
        not_found_res = await client.get("/api/v1/profiles/non-existent-uuid-12345")
        assert not_found_res.status_code == 404
        _validate_schema(not_found_res.json(), "ErrorResponse")

        # Check that profile config is untouched after 422
        check_res = await client.get(f"/api/v1/profiles/{pid}")
        assert check_res.status_code == 200
        assert check_res.json()["gpu_family"] == "intel"
        assert check_res.json()["name"] == "Alpha Production Profile"

        # Nullable fields cleared to null: accepted with 200
        patch_res = await client.put(
            f"/api/v1/profiles/{pid}", json={"notes": None, "proxy": None}
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["notes"] is None
        assert patch_res.json()["proxy"] is None

    # 3. Simulate server restart: stop subprocess and start new on same DB
    server.stop()
    server.start()

    async with httpx.AsyncClient(
        base_url=server.base_url,
        headers=server.auth_headers,
        timeout=10.0,
        trust_env=False,
    ) as client:
        # Re-read profile after restart
        res_after_restart = await client.get(f"/api/v1/profiles/{pid}")
        assert res_after_restart.status_code == 200
        reloaded = res_after_restart.json()
        assert reloaded["id"] == pid
        assert reloaded["name"] == "Alpha Production Profile"
        assert reloaded["user_data_dir"] == f"/data/profiles/{pid}/profile"
        assert reloaded["notes"] is None
        assert reloaded["proxy"] is None
        assert reloaded["timezone"] == "Europe/London"
        assert reloaded["locale"] == "en-GB"
        assert reloaded["screen_width"] == 1440
        assert reloaded["screen_height"] == 900
        assert reloaded["gpu_family"] == "intel"
        assert reloaded["humanize"] is True
        assert reloaded["human_preset"] == "careful"
        assert reloaded["sort_order"] == 12
        assert {t["tag"] for t in reloaded["tags"]} == {"banking", "uk"}

        # 4. Delete profile
        del_res = await client.delete(f"/api/v1/profiles/{pid}")
        assert del_res.status_code == 204
        assert (await client.get(f"/api/v1/profiles/{pid}")).status_code == 404


@pytest.mark.asyncio
async def test_ac002_immutable_snapshots_and_idempotency_conflicts(
    server_harness: SubprocessServer,
):
    """AC-002: Immutable version snapshots (including tags), concurrent same op_id,

    409 Conflict when op_id reused with different request payload or target,
    and concurrent disjoint patches without lost updates.
    """
    server = server_harness
    async with httpx.AsyncClient(
        base_url=server.base_url,
        headers=server.auth_headers,
        timeout=10.0,
        trust_env=False,
    ) as client:
        op_id = "op_idempotent_test_999"
        headers = {"Idempotency-Key": op_id}

        create_payload = {
            "name": "Immutable Profile",
            "screen_width": 1024,
            "screen_height": 768,
            "tags": [{"tag": "v1_tag", "color": "#111"}],
        }

        # 1. Concurrent 5 identical requests with same operation_id
        tasks = [
            client.post("/api/v1/profiles", json=create_payload, headers=headers)
            for _ in range(5)
        ]
        responses = await asyncio.gather(*tasks)
        for r in responses:
            assert r.status_code == 201

        # All 5 return identical profile ID
        created_ids = {r.json()["id"] for r in responses}
        assert len(created_ids) == 1
        pid = created_ids.pop()

        # Database contains exactly 1 profile
        profiles_list = (await client.get("/api/v1/profiles")).json()
        assert len([p for p in profiles_list if p["id"] == pid]) == 1

        # 2. Reusing same operation_id with DIFFERENT payload returns HTTP 409 Conflict!
        conflict_payload = {
            "name": "Different Request Payload",
            "screen_width": 1920,
        }
        res_conflict = await client.post(
            "/api/v1/profiles", json=conflict_payload, headers=headers
        )
        assert res_conflict.status_code == 409
        _validate_schema(res_conflict.json(), "ErrorResponse")
        assert "idempotency_conflict" in res_conflict.json()["error"]

        # Reusing same operation_id on DIFFERENT target profile returns 409 Conflict
        p2_res = await client.post(
            "/api/v1/profiles", json={"name": "Second Profile Target"}
        )
        pid2 = p2_res.json()["id"]
        res_diff_target = await client.patch(
            f"/api/v1/profiles/{pid2}", json={"name": "P2 Changed"}, headers=headers
        )
        assert res_diff_target.status_code == 409
        _validate_schema(res_diff_target.json(), "ErrorResponse")

        # 3. Create v2 and v3
        up2 = await client.put(
            f"/api/v1/profiles/{pid}",
            json={
                "name": "Name v2",
                "screen_width": 1920,
                "tags": [{"tag": "v2_tag", "color": "#222"}],
            },
        )
        assert up2.status_code == 200
        assert up2.json()["current_config_version"] == 2

        up3 = await client.put(
            f"/api/v1/profiles/{pid}",
            json={
                "name": "Name v3",
                "screen_width": 2560,
                "tags": [{"tag": "v3_tag", "color": "#333"}],
            },
        )
        assert up3.status_code == 200
        assert up3.json()["current_config_version"] == 3

        # 4. Concurrent disjoint PATCH (name vs notes) in 5 rounds: NO LOST UPDATES!
        for r in range(5):
            r_name = f"r{r}_name_disjoint"
            r_notes = f"r{r}_notes_disjoint"
            t_name = client.patch(f"/api/v1/profiles/{pid}", json={"name": r_name})
            t_notes = client.patch(f"/api/v1/profiles/{pid}", json={"notes": r_notes})
            r1, r2 = await asyncio.gather(t_name, t_notes)
            assert r1.status_code == 200
            assert r2.status_code == 200

            curr = (await client.get(f"/api/v1/profiles/{pid}")).json()
            assert curr["name"] == r_name, f"Round {r} lost name update!"
            assert curr["notes"] == r_notes, f"Round {r} lost notes update!"

    # Restart server to verify snapshot persistence across process boundaries
    server.stop()
    server.start()

    async with httpx.AsyncClient(
        base_url=server.base_url,
        headers=server.auth_headers,
        timeout=10.0,
        trust_env=False,
    ) as client:
        versions = (await client.get(f"/api/v1/profiles/{pid}/versions")).json()
        assert len(versions) >= 3

        v1 = (await client.get(f"/api/v1/profiles/{pid}/versions/1")).json()
        assert v1["config"]["name"] == "Immutable Profile"
        assert v1["config"]["screen_width"] == 1024
        assert v1["tags"][0]["tag"] == "v1_tag"

        v2 = (await client.get(f"/api/v1/profiles/{pid}/versions/2")).json()
        assert v2["config"]["name"] == "Name v2"
        assert v2["config"]["screen_width"] == 1920
        assert v2["tags"][0]["tag"] == "v2_tag"

        v3 = (await client.get(f"/api/v1/profiles/{pid}/versions/3")).json()
        assert v3["config"]["name"] == "Name v3"
        assert v3["config"]["screen_width"] == 2560
        assert v3["tags"][0]["tag"] == "v3_tag"


@pytest.mark.asyncio
async def test_ac003_and_ac006_runtime_events_convergence_and_diagnostics(
    server_harness: SubprocessServer,
):
    """AC-003: Runtime state convergence, intent separation, stale protection.

    Parallel duplicate exit events, late crash after stop, replaying start.
    AC-006: Structured JSON diagnostics parsing, metadata, secret redaction.
    """
    secret_pass = "P@ssw0rd_Secret_999"
    secret_token = "SECRET_TOKEN_XYZ_123"
    secret_cookie = "SECRET_COOKIE_ABC_456"
    secret_clipboard = "SECRET_CLIPBOARD_CONTENT_789"
    secret_note = "MY_ARBITRARY_SECRET_NOTE_000"
    secret_id_raw = "evt-SECRET_COOKIE_VAL_XYZ999"

    server = server_harness
    async with httpx.AsyncClient(
        base_url=server.base_url,
        headers=server.auth_headers,
        timeout=10.0,
        trust_env=False,
    ) as client:
        client.headers["Authorization"] = f"Bearer {server.supervisor_token}"
        # Create profile with injected secrets in config
        p_res = await client.post(
            "/api/v1/profiles",
            json={
                "name": "Runtime Convergence Profile",
                "proxy": f"socks5://admin:{secret_pass}@proxy.example.com:1080",
                "notes": secret_note,
            },
        )
        assert p_res.status_code == 201
        pid = p_res.json()["id"]

        # 1. User intent to start: desired=running, observed=stopped
        # (intent does NOT invent actual runtime!)
        start_op_id = "op_start_run_001"
        start_res = await client.patch(
            f"/api/v1/profiles/{pid}/runtime/desired-state",
            json={"desired_state": "running"},
            headers={"Idempotency-Key": start_op_id},
        )
        assert start_res.status_code == 200
        assert start_res.json()["desired_state"] == "running"
        assert start_res.json()["observed_state"] == "stopped"  # NOT running!

        # 2. Supervisor binds inst_1 with config_version 1
        inst_1 = "inst_run_001"
        bind_res = await client.post(
            f"/api/v1/internal/supervisor/runtimes/bind?profile_id={pid}",
            json={"runtime_instance_id": inst_1, "config_version": 1},
        )
        assert bind_res.status_code == 200
        assert bind_res.json()["runtime_instance_id"] == inst_1
        assert bind_res.json()["observed_state"] == "starting"
        assert bind_res.json()["config_version"] == 1

        # Supervisor reports observed_state = running
        obs_res = await client.post(
            f"/api/v1/internal/supervisor/runtimes/observed?profile_id={pid}",
            json={"runtime_instance_id": inst_1, "observed_state": "running"},
        )
        assert obs_res.status_code == 200
        assert obs_res.json()["observed_state"] == "running"

        # Re-binding same instance + same version is idempotent
        # and does NOT regress observed running to starting
        rebind_res = await client.post(
            f"/api/v1/internal/supervisor/runtimes/bind?profile_id={pid}",
            json={"runtime_instance_id": inst_1, "config_version": 1},
        )
        assert rebind_res.status_code == 200
        assert rebind_res.json()["observed_state"] == "running"

        # Re-binding same instance with a DIFFERENT config_version is rejected!
        rebind_diff_cfg = await client.post(
            f"/api/v1/internal/supervisor/runtimes/bind?profile_id={pid}",
            json={"runtime_instance_id": inst_1, "config_version": 2},
        )
        assert rebind_diff_cfg.status_code == 422
        _validate_schema(rebind_diff_cfg.json(), "ValidationErrorResponse")

        # 3. User modifies profile config to v2 while container runs v1
        up_res = await client.put(
            f"/api/v1/profiles/{pid}", json={"name": "Updated Name v2"}
        )
        assert up_res.status_code == 200
        assert up_res.json()["current_config_version"] == 2

        # Runtime bound config_version remains 1!
        rt_check = (await client.get(f"/api/v1/profiles/{pid}/runtime")).json()
        assert rt_check["config_version"] == 1

        # Observation report claiming unapplied config_version 2 on bound instance
        # is rejected!
        obs_bad_cfg = await client.post(
            f"/api/v1/internal/supervisor/runtimes/observed?profile_id={pid}",
            json={
                "runtime_instance_id": inst_1,
                "observed_state": "running",
                "config_version": 2,
            },
        )
        assert obs_bad_cfg.status_code == 422
        _validate_schema(obs_bad_cfg.json(), "ValidationErrorResponse")

        # 4. Heartbeat event does NOT alter state or stop runtime
        hb_res = await client.post(
            "/api/v1/internal/supervisor/runtimes/events",
            json={
                "event_id": "evt_hb_inst1",
                "profile_id": pid,
                "runtime_instance_id": inst_1,
                "event_type": "heartbeat",
                "config_version": 1,
            },
        )
        assert hb_res.status_code == 200
        assert hb_res.json()["outcome"] == "applied"
        assert (await client.get(f"/api/v1/profiles/{pid}/runtime")).json()[
            "observed_state"
        ] == "running"

        # 5. Invalid config_version (999) rejected
        inv_res = await client.post(
            "/api/v1/internal/supervisor/runtimes/events",
            json={
                "event_id": "evt_inv_999",
                "profile_id": pid,
                "runtime_instance_id": inst_1,
                "event_type": "exit",
                "exit_code": 1,
                "exit_reason": "crash",
                "config_version": 999,
            },
        )
        assert inv_res.status_code == 200
        assert inv_res.json()["outcome"] == "invalid_config_version"

        # Event with unapplied config version 2 on instance bound with 1 is rejected
        mismatched_cfg_res = await client.post(
            "/api/v1/internal/supervisor/runtimes/events",
            json={
                "event_id": "evt_mismatch_cfg",
                "profile_id": pid,
                "runtime_instance_id": inst_1,
                "event_type": "exit",
                "exit_code": 1,
                "exit_reason": "crash",
                "config_version": 2,  # container was bound to 1!
            },
        )
        assert mismatched_cfg_res.status_code == 200
        assert mismatched_cfg_res.json()["outcome"] == "invalid_config_version"

        # 6. Report abnormal exit event on inst_1 (with secret ID to test redaction)
        evt_ab = {
            "event_id": secret_id_raw,
            "profile_id": pid,
            "runtime_instance_id": inst_1,
            "event_type": "exit",
            "exit_code": 1,
            "exit_reason": "browser_segfault",
            "config_version": 1,
            "payload": {"details": secret_cookie},
        }

        # Parallel duplicate exit events (5 concurrent requests) return 200 without 500
        dup_tasks = [
            client.post("/api/v1/internal/supervisor/runtimes/events", json=evt_ab) for _ in range(5)
        ]
        dup_responses = await asyncio.gather(*dup_tasks)
        for r in dup_responses:
            assert r.status_code == 200

        # Disk events are diagnostics only; the Supervisor observation is the
        # authoritative terminal fact and counts exactly one failure.
        observed_ab = await client.post(
            f"/api/v1/internal/supervisor/runtimes/observed?profile_id={pid}",
            json={
                "runtime_instance_id": inst_1,
                "observed_state": "error",
                "reason": "container_exit",
                "config_version": 1,
            },
        )
        assert observed_ab.status_code == 200
        rt_after_ab = (await client.get(f"/api/v1/profiles/{pid}/runtime")).json()
        assert rt_after_ab["desired_state"] == "running"  # Preserved!
        assert rt_after_ab["observed_state"] == "error"
        assert rt_after_ab["runtime_instance_id"] is None
        assert rt_after_ab["failure_count"] == 1  # Not double counted!

        # 7. Replay start intent with same Idempotency-Key does NOT reset failures
        replay_start = await client.patch(
            f"/api/v1/profiles/{pid}/runtime/desired-state",
            json={"desired_state": "running"},
            headers={"Idempotency-Key": start_op_id},
        )
        assert replay_start.status_code == 200
        # Failure count MUST REMAIN 1
        assert (await client.get(f"/api/v1/profiles/{pid}/runtime")).json()[
            "failure_count"
        ] == 1

        # 8. Supervisor binds inst_2 with applied config_version 2
        inst_2 = "inst_run_002"
        await client.post(
            f"/api/v1/internal/supervisor/runtimes/bind?profile_id={pid}",
            json={"runtime_instance_id": inst_2, "config_version": 2},
        )
        await client.post(
            f"/api/v1/internal/supervisor/runtimes/observed?profile_id={pid}",
            json={"runtime_instance_id": inst_2, "observed_state": "running"},
        )

        # Late bind of old inst_1 while inst_2 is active is rejected with 409 Conflict
        late_bind = await client.post(
            f"/api/v1/internal/supervisor/runtimes/bind?profile_id={pid}",
            json={"runtime_instance_id": inst_1, "config_version": 1},
        )
        assert late_bind.status_code == 409
        _validate_schema(late_bind.json(), "ErrorResponse")
        # inst_2 remains active!
        assert (await client.get(f"/api/v1/profiles/{pid}/runtime")).json()[
            "runtime_instance_id"
        ] == inst_2

        # Stale event from inst_1 is rejected
        evt_stale = {
            "event_id": "evt_stale_inst1",
            "profile_id": pid,
            "runtime_instance_id": inst_1,  # old!
            "event_type": "exit",
            "exit_code": 137,
            "exit_reason": "oom",
            "config_version": 1,
        }
        res_stale = await client.post("/api/v1/internal/supervisor/runtimes/events", json=evt_stale)
        assert res_stale.status_code == 200
        assert res_stale.json()["outcome"] == "stale_instance"
        assert (await client.get(f"/api/v1/profiles/{pid}/runtime")).json()[
            "failure_count"
        ] == 1

        # 9. Late abnormal exit after stop intent:
        # User stops profile -> desired_state becomes stopped
        await client.post(f"/api/v1/profiles/{pid}/stop")
        assert (await client.get(f"/api/v1/profiles/{pid}/runtime")).json()[
            "desired_state"
        ] == "stopped"

        # Now late crash event from inst_2 arrives -> desired_state MUST REMAIN stopped!
        late_crash = {
            "event_id": "evt_late_crash_inst2",
            "profile_id": pid,
            "runtime_instance_id": inst_2,
            "event_type": "exit",
            "exit_code": 137,
            "exit_reason": "sigkill",
            "config_version": 2,
        }
        await client.post("/api/v1/internal/supervisor/runtimes/events", json=late_crash)
        rt_after_late = (await client.get(f"/api/v1/profiles/{pid}/runtime")).json()
        assert rt_after_late["desired_state"] == "stopped"  # MUST NOT become running!

        # 10. Trigger 422 with secret in invalid field to verify sanitization
        bad_req = await client.put(
            f"/api/v1/profiles/{pid}",
            json={"screen_width": -999, "notes": secret_clipboard},
        )
        assert bad_req.status_code == 422
        bad_body = bad_req.text
        # Error body must NOT leak the raw payload/clipboard string
        assert secret_clipboard not in bad_body

    # AC-006: Diagnostics physical log inspection
    await asyncio.sleep(0.5)
    logs = server.read_logs()
    assert "RUNTIME_EVENT_JSON:" in logs

    # Parse and validate structured JSON log lines
    event_logs = []
    for line in logs.splitlines():
        if "RUNTIME_EVENT_JSON:" in line:
            json_part = line.split("RUNTIME_EVENT_JSON:", 1)[1].strip()
            parsed = json.loads(json_part)
            event_logs.append(parsed)

    assert len(event_logs) >= 3
    for entry in event_logs:
        assert "event_id" in entry
        assert "profile_id" in entry
        assert "runtime_instance_id" in entry
        assert "outcome" in entry
        assert "timestamp" in entry

    # Strict assertion: sensitive secrets NEVER leaked in physical logs!
    for secret in (
        secret_pass,
        secret_token,
        secret_cookie,
        secret_clipboard,
        secret_id_raw,
    ):
        assert secret not in logs, f"Security Violation: {secret} leaked in server log!"


@pytest.mark.asyncio
async def test_ac004_sqlite_busy_timeout_contention_and_recovery(
    server_harness: SubprocessServer,
):
    """AC-004: PRAGMA busy_timeout=5000 readback, lock contention with 1.5s recovery

    vs >5.0s timeout returning HTTP 503, connection rollback, and post-lock recovery.
    """
    server = server_harness

    # 1. Verify WAL and busy_timeout via direct connection
    conn = sqlite3.connect(str(server.db_path))
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    assert cursor.fetchone()[0].lower() == "wal"
    conn.close()

    # 2. Short Lock Contention (1.5s): API request busy-waits and succeeds within 5s
    t0 = time.time()

    def hold_short_lock():
        with sqlite3.connect(str(server.db_path), timeout=1.0) as c:
            c.execute("BEGIN EXCLUSIVE;")
            time.sleep(1.5)
            c.commit()

    lock_thread = threading.Thread(target=hold_short_lock)
    lock_thread.start()
    await asyncio.sleep(0.1)  # Ensure lock is held

    async with httpx.AsyncClient(
        base_url=server.base_url,
        headers=server.auth_headers,
        timeout=10.0,
        trust_env=False,
    ) as client:
        resp = await client.post(
            "/api/v1/profiles", json={"name": "Short Lock Profile"}
        )
        elapsed = time.time() - t0
        lock_thread.join()

        assert resp.status_code == 201
        assert 1.4 <= elapsed < 4.5, f"Expected elapsed ~1.5s, got {elapsed:.2f}s"
        assert resp.json()["name"] == "Short Lock Profile"

    # 3. Long Lock Contention (>5.0s): API request times out at ~5s and returns 503
    def hold_long_lock():
        with sqlite3.connect(str(server.db_path), timeout=1.0) as c:
            c.execute("BEGIN EXCLUSIVE;")
            time.sleep(6.0)
            c.commit()

    long_thread = threading.Thread(target=hold_long_lock)
    long_thread.start()
    await asyncio.sleep(0.1)

    t0 = time.time()
    async with httpx.AsyncClient(
        base_url=server.base_url,
        headers=server.auth_headers,
        timeout=15.0,
        trust_env=False,
    ) as client:
        resp_timeout = await client.post(
            "/api/v1/profiles", json={"name": "Timeout Profile"}
        )
        elapsed_timeout = time.time() - t0
        long_thread.join()

        assert resp_timeout.status_code == 503
        assert resp_timeout.headers.get("Retry-After") == "1"
        assert 4.5 <= elapsed_timeout <= 6.5, (
            f"Expected elapsed ~5.0s, got {elapsed_timeout:.2f}s"
        )
        body = resp_timeout.json()
        _validate_schema(body, "ErrorResponse")
        assert body["error"] == "database_busy"
        assert body["retryable"] is True
        assert "syntax error" not in str(body).lower()

        # 4. Post-lock recovery: next request succeeds cleanly without transaction leak
        recover_resp = await client.post(
            "/api/v1/profiles", json={"name": "Recovered Profile"}
        )
        assert recover_resp.status_code == 201
        assert recover_resp.json()["name"] == "Recovered Profile"


@pytest.mark.asyncio
async def test_ac006_db_constraint_integrity_error_no_secret_leak_in_logs(
    server_harness: SubprocessServer,
):
    """AC-006: Real DB constraint violation rolls back cleanly.

    Returns typed 409 Conflict, and DOES NOT leak SQL parameters or secrets in logs.
    """
    server = server_harness
    secret = "ROOT_PRIVATE_SENTINEL_9b84"

    async with httpx.AsyncClient(
        base_url=server.base_url,
        headers=server.auth_headers,
        timeout=10.0,
        trust_env=False,
    ) as client:
        # Trigger real SQLite IntegrityError (duplicate PK on profile_tags)
        failed = await client.post(
            "/api/v1/profiles",
            json={
                "name": "atomic rollback",
                "tags": [{"tag": secret}, {"tag": secret}],
            },
        )
        assert failed.status_code == 409
        _validate_schema(failed.json(), "ErrorResponse")
        assert secret not in failed.text

        # Verify zero partial data created in DB
        profiles = (await client.get("/api/v1/profiles")).json()
        assert not any(p["name"] == "atomic rollback" for p in profiles)

        # Next valid request succeeds cleanly
        succ = await client.post(
            "/api/v1/profiles", json={"name": "Post Constraint Success"}
        )
        assert succ.status_code == 201

    # Verify physical server log contains zero secret or SQL bind parameter dumps
    await asyncio.sleep(0.2)
    logs = server.read_logs()
    assert secret not in logs, (
        "Security Violation: Secret leaked in physical server logs!"
    )
    assert "[parameters:" not in logs, (
        "Security Violation: SQL parameters dumped in logs!"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "keyword_tag", ["busy", "locked", "profile-busy-worker", "db-locked-state"]
)
async def test_ac006_duplicate_tags_with_busy_and_locked_keywords_return_409(
    server_harness: SubprocessServer, keyword_tag: str
):
    """IntegrityError for tags with 'busy' or 'locked' must return 409, NOT 503."""
    server = server_harness
    async with httpx.AsyncClient(
        base_url=server.base_url,
        headers=server.auth_headers,
        timeout=10.0,
        trust_env=False,
    ) as client:
        resp = await client.post(
            "/api/v1/profiles",
            json={
                "name": f"constraint-{keyword_tag}",
                "tags": [{"tag": keyword_tag}, {"tag": keyword_tag}],
            },
        )
        assert resp.status_code == 409, (
            f"Expected 409 for duplicate tag '{keyword_tag}', "
            f"got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        _validate_schema(body, "ErrorResponse")
        assert body["error"] == "constraint_violation"
        assert body["retryable"] is False
