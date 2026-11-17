import asyncio
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error

WORKDIR = os.path.abspath(os.path.dirname(__file__))

# ISOLATED STORAGE DIRECTORIES
API_STORAGE_DIR = os.path.join(WORKDIR, "api_storage")
DB_PATH = os.path.join(API_STORAGE_DIR, "cbrowser.db")

RUNTIME_DIR = os.path.join(WORKDIR, "runtime")

ROLES_PY = os.path.join(WORKDIR, "roles.py")
AGENT_PY = os.path.join(WORKDIR, "container_agent.py")

PROFILE_ID = "prof_rec_1"
CONTAINER_NAME = f"cbrowser-spike-recovery-runtime-{PROFILE_ID}"

def log(msg):
    print(f"[{time.strftime('%X')}][ORCHESTRATOR] {msg}", flush=True)

def cleanup_docker():
    try:
        out = subprocess.check_output(
            ["docker", "ps", "-a", "--filter", "name=cbrowser-spike-recovery", "--format", "{{.Names}}"]
        ).decode().split()
        for name in out:
            subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log(f"Docker cleanup warning: {e}")

def send_uds_command_via_container(container_name, cmd_dict, timeout=5.0):
    cmd_json = json.dumps(cmd_dict)
    py_code = f"""
import socket, json
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout({timeout})
s.connect("/app_run/agent.sock")
s.sendall(json.dumps({cmd_dict}).encode() + b"\\n")
res = s.recv(4096)
print(res.decode().strip())
s.close()
"""
    out = subprocess.check_output(
        ["docker", "exec", container_name, "python3", "-c", py_code],
        stderr=subprocess.DEVNULL
    ).decode().strip()
    return json.loads(out)

async def run_suite():
    # 0. Clean and setup directories
    if os.path.exists(API_STORAGE_DIR):
        shutil.rmtree(API_STORAGE_DIR)
    if os.path.exists(RUNTIME_DIR):
        shutil.rmtree(RUNTIME_DIR)

    os.makedirs(API_STORAGE_DIR, exist_ok=True)
    os.makedirs(RUNTIME_DIR, exist_ok=True)

    # Copy agent script into runtime dir so container can mount it
    shutil.copy(AGENT_PY, os.path.join(RUNTIME_DIR, "container_agent.py"))

    cleanup_docker()

    # Generate random secret token (never output to logs)
    token = secrets.token_hex(16)
    api_port = 58083
    api_url = f"http://127.0.0.1:{api_port}"

    api_proc = None
    sup_proc = None

    try:
        # 1. Start Independent Real HTTP API Process
        log(f"[Step 1] Starting independent API service process on port {api_port}...")
        api_proc = subprocess.Popen(
            [sys.executable, ROLES_PY, "--role", "api", "--db-path", DB_PATH, "--port", str(api_port), "--token", token]
        )
        for _ in range(30):
            await asyncio.sleep(0.2)
            try:
                req = urllib.request.Request(f"{api_url}/api/desired-state/{PROFILE_ID}", headers={"Authorization": f"Bearer {token}"})
                with urllib.request.urlopen(req, timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                pass
        log("[Step 1] API Service confirmed online.")

        # Set initial desired_state = running
        initial_instance_id = "inst_live_001"
        req = urllib.request.Request(
            f"{api_url}/api/set-desired-state",
            data=json.dumps({"profile_id": PROFILE_ID, "desired_state": "running", "runtime_instance_id": initial_instance_id}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            assert resp.status == 200
        log(f"[Step 2] Desired state set to running (instance={initial_instance_id})")

        # 2. Start Independent Real Supervisor Process (only points to RUNTIME_DIR, NO db_path)
        log("[Step 3] Starting independent Supervisor service process (mounts ONLY RUNTIME_DIR)...")
        sup_proc = subprocess.Popen(
            [sys.executable, ROLES_PY, "--role", "supervisor", "--api-url", api_url, "--token", token, "--run-dir", RUNTIME_DIR, "--profile-id", PROFILE_ID]
        )

        # Wait for Supervisor to launch CloakBrowser container
        uds_path = os.path.join(RUNTIME_DIR, "agent.sock")
        log("[Step 4] Waiting for Supervisor to launch CloakBrowser container and UDS agent.sock...")
        container_started = False
        pong = None
        for _ in range(60):
            await asyncio.sleep(0.5)
            if os.path.exists(uds_path):
                try:
                    pong = send_uds_command_via_container(CONTAINER_NAME, {"id": 1, "cmd": "ping"}, timeout=1.0)
                    if pong and pong.get("status") == "pong":
                        container_started = True
                        break
                except Exception:
                    pass

        assert container_started, "Docker CloakBrowser container / Agent UDS failed to respond to ping!"
        log(f"[Step 4] Agent UDS ping reply verified: {pong}")

        # NEGATIVE PROOF: Verify SQLite database is completely inaccessible inside container!
        log("[Step 4b] Negative Verification: inspecting container mounts & attempting SQLite file access inside container...")
        mounts_json = subprocess.check_output(
            ["docker", "inspect", "-f", "{{json .Mounts}}", CONTAINER_NAME]
        ).decode().strip()
        log(f"[Step 4b] Docker container mounts: {mounts_json}")
        # Verify API_STORAGE_DIR is not mounted anywhere
        assert API_STORAGE_DIR not in mounts_json, "SECURITY BREACH: api_storage was mounted to container!"
        # Verify accessing cbrowser.db inside container fails
        check_db_res = subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "ls", "/app_run/cbrowser.db"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        assert check_db_res.returncode != 0, "SECURITY BREACH: cbrowser.db was found inside container!"
        log("[Step 4b] Negative Verification PASSED: SQLite database does not exist inside container.")

        # 3. Terminate API Process (Simulating API Offline)
        log("[Step 5] KILLING API PROCESS (Simulating API Offline)...")
        api_proc.terminate()
        api_proc.wait(timeout=3)
        api_proc = None
        log("[Step 5] API is now completely OFFLINE.")

        # 4. Trigger Real Browser Close via UDS RPC -> CDP Browser.close
        log("[Step 6] Sending 'close_browser' RPC via UDS (triggers CDP Browser.close in Chrome)...")
        close_reply = send_uds_command_via_container(CONTAINER_NAME, {"id": 2, "cmd": "close_browser"}, timeout=3.0)
        log(f"[Step 6] close_browser reply: {close_reply}")
        assert close_reply.get("status") == "ok"

        # Wait for browser process exit and persistent exit event
        log("[Step 7] Waiting for browser process exit and persistent exit event...")
        events_file = os.path.join(RUNTIME_DIR, "events.jsonl")
        sup_queue_file = os.path.join(RUNTIME_DIR, "supervisor_queue.jsonl")

        event_captured = None
        for _ in range(40):
            await asyncio.sleep(0.5)
            if os.path.exists(sup_queue_file):
                with open(sup_queue_file, "r") as f:
                    lines = [l.strip() for l in f if l.strip()]
                    if lines:
                        event_captured = json.loads(lines[0])
                        break
            elif os.path.exists(events_file):
                with open(events_file, "r") as f:
                    lines = [l.strip() for l in f if l.strip()]
                    if lines:
                        event_captured = json.loads(lines[0])
                        break

        assert event_captured, "Failed to capture persistent exit event while API offline!"
        log(f"[Step 7] Verified on-disk persistent exit event while API was dead: {event_captured}")
        assert event_captured["exit_code"] == 0
        assert event_captured["runtime_instance_id"] == initial_instance_id

        # 5. SIGKILL SUPERVISOR BEFORE DRAIN TEST (Crash recovery checkpoint)
        log("[Step 8] Testing Supervisor Crash Recovery with SIGKILL...")
        sup_proc.terminate()
        sup_proc.wait(timeout=3)

        # Start Supervisor with --sigkill-before-drain to trigger SIGKILL immediately after ingestion
        log("[Step 8a] Launching Supervisor configured to SIGKILL itself before draining to API...")
        crash_sup_proc = subprocess.Popen(
            [sys.executable, ROLES_PY, "--role", "supervisor", "--api-url", api_url, "--token", token, "--run-dir", RUNTIME_DIR, "--profile-id", PROFILE_ID, "--sigkill-before-drain"]
        )
        ret = crash_sup_proc.wait(timeout=5)
        log(f"[Step 8a] Supervisor crashed with exit status: {ret}")

        # Check that queue was NOT lost or corrupted by SIGKILL!
        assert os.path.exists(sup_queue_file), "Supervisor queue was lost after SIGKILL!"
        with open(sup_queue_file, "r") as f:
            q_lines = [l.strip() for l in f if l.strip()]
        assert len(q_lines) > 0, "Supervisor queue was truncated or empty after SIGKILL!"
        log(f"[Step 8b] Verified: Persistent queue intact on disk with {len(q_lines)} event(s) after SIGKILL crash!")

        # 6. Restart Normal Supervisor (API still offline)
        log("[Step 8c] Restarting normal Supervisor (API still offline)...")
        sup_proc = subprocess.Popen(
            [sys.executable, ROLES_PY, "--role", "supervisor", "--api-url", api_url, "--token", token, "--run-dir", RUNTIME_DIR, "--profile-id", PROFILE_ID]
        )
        await asyncio.sleep(2.0)
        assert os.path.exists(sup_queue_file), "Queue lost after supervisor restart!"

        # 7. Restart API Process and Drain Events
        log("[Step 9] RESTARTING API SERVICE PROCESS...")
        api_proc = subprocess.Popen(
            [sys.executable, ROLES_PY, "--role", "api", "--db-path", DB_PATH, "--port", str(api_port), "--token", token]
        )
        for _ in range(30):
            await asyncio.sleep(0.2)
            try:
                req = urllib.request.Request(f"{api_url}/api/desired-state/{PROFILE_ID}", headers={"Authorization": f"Bearer {token}"})
                with urllib.request.urlopen(req, timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                pass
        log("[Step 9] API service restarted. Supervisor will drain persistent event queue.")

        # Wait for Supervisor to drain events to API
        for _ in range(30):
            await asyncio.sleep(0.5)
            if not os.path.exists(sup_queue_file):
                break

        # Check API desired_state is now STOPPED
        req = urllib.request.Request(f"{api_url}/api/desired-state/{PROFILE_ID}", headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            st = json.loads(resp.read().decode())
        log(f"[Step 10] API current state: {st}")
        assert st["desired_state"] == "stopped", f"Expected desired_state='stopped', got {st['desired_state']}"
        assert st["observed_state"] == "stopped"

        # 8. Multi-Round Reconcile Verification
        log("[Step 11] Running 5 rounds of reconciliation to confirm NO ghost-restarts...")
        for i in range(5):
            await asyncio.sleep(1.0)
            running = subprocess.check_output(
                ["docker", "ps", "--filter", f"name={CONTAINER_NAME}", "--format", "{{.Names}}"]
            ).decode().strip()
            assert not running, f"Browser container was mistakenly restarted in round {i+1}!"
        log("[Step 11] 5 reconcile rounds completed: container remained stopped.")

        # 9. Replay Duplicate Event Test
        log("[Step 12] Replaying duplicate exit event to API...")
        req = urllib.request.Request(
            f"{api_url}/api/report-exit-event",
            data=json.dumps(event_captured).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            dup_res = json.loads(resp.read().decode())
        log(f"[Step 12] Duplicate replay response: {dup_res}")
        assert dup_res["status"] == "duplicate_ignored"

        # 10. REAL NEW INSTANCE VERIFICATION & STALE EVENT REJECTION
        log("[Step 13] REAL NEW INSTANCE LAUNCH: Setting desired_state=running with new instance_id='inst_new_002'...")
        new_instance_id = "inst_new_002"
        req = urllib.request.Request(
            f"{api_url}/api/set-desired-state",
            data=json.dumps({"profile_id": PROFILE_ID, "desired_state": "running", "runtime_instance_id": new_instance_id}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            assert resp.status == 200

        # Wait for Supervisor to launch the REAL new Docker container
        log("[Step 13a] Waiting for Supervisor to launch the REAL new Docker container for inst_new_002...")
        new_container_ready = False
        new_pong = None
        for _ in range(60):
            await asyncio.sleep(0.5)
            try:
                new_pong = send_uds_command_via_container(CONTAINER_NAME, {"id": 10, "cmd": "ping"}, timeout=1.0)
                if new_pong and new_pong.get("runtime_instance_id") == new_instance_id:
                    new_container_ready = True
                    break
            except Exception:
                pass

        assert new_container_ready, "Real new Docker container for inst_new_002 failed to launch / respond to ping!"
        log(f"[Step 13a] Real new container is online and verified via UDS: {new_pong}")

        # Now inject stale exit event from OLD instance (inst_live_001)
        log("[Step 13b] Injecting stale exit event from old instance (inst_live_001)...")
        stale_event = {
            "event_id": "evt_stale_delayed_999",
            "profile_id": PROFILE_ID,
            "runtime_instance_id": initial_instance_id,  # STALE OLD INSTANCE!
            "exit_code": 0,
            "exit_reason": "late_arriving_exit",
            "timestamp": time.time(),
        }
        req = urllib.request.Request(
            f"{api_url}/api/report-exit-event",
            data=json.dumps(stale_event).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            stale_res = json.loads(resp.read().decode())
        log(f"[Step 13b] Stale event report response: {stale_res}")
        assert stale_res["status"] == "stale_instance_rejected"

        # Verify new instance desired_state was NOT stopped
        req = urllib.request.Request(f"{api_url}/api/desired-state/{PROFILE_ID}", headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            st_new = json.loads(resp.read().decode())
        log(f"[Step 13b] API state after stale event: {st_new}")
        assert st_new["desired_state"] == "running", "Stale exit event mistakenly killed new instance!"
        assert st_new["runtime_instance_id"] == new_instance_id

        # Verify new container continues running smoothly over multiple reconcile steps
        log("[Step 13c] Verifying new container remains running over multiple reconcile steps...")
        for i in range(3):
            await asyncio.sleep(1.0)
            running = subprocess.check_output(
                ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER_NAME]
            ).decode().strip()
            assert running == "true", f"New container stopped unexpectedly in round {i+1}!"
        log("[Step 13c] Verified: New container remains running unaffected by stale event.")

        log(">>> ALL REAL PROCESS / DOCKER / API RESTART & RECOVERY CHECKS PASSED FULLY! <<<")

    finally:
        log("Tearing down processes and Docker containers...")
        if sup_proc:
            sup_proc.terminate()
            try:
                sup_proc.wait(timeout=2)
            except Exception:
                sup_proc.kill()
        if api_proc:
            api_proc.terminate()
            try:
                api_proc.wait(timeout=2)
            except Exception:
                api_proc.kill()
        cleanup_docker()
        log("Teardown complete.")

async def main():
    try:
        await asyncio.wait_for(run_suite(), timeout=120.0)
    except TimeoutError:
        log("ERROR: Global test suite timeout (120s) exceeded!")
        cleanup_docker()
        raise

if __name__ == "__main__":
    asyncio.run(main())
