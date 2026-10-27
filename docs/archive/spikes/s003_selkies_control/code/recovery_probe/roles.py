import argparse
import http.server
import json
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error

def log(role, msg):
    print(f"[{time.strftime('%X')}][{role}] {msg}", flush=True)

# -------------------------------------------------------------
# ROLE: API SERVICE (Sole SQLite writer)
# -------------------------------------------------------------
class ApiHttpHandler(http.server.BaseHTTPRequestHandler):
    db_path = None
    auth_token = None

    def _check_auth(self):
        auth = self.headers.get("Authorization", "")
        if auth != f"Bearer {self.auth_token}":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error": "unauthorized"}')
            return False
        return True

    def do_GET(self):
        if not self._check_auth():
            return
        if self.path.startswith("/api/desired-state/"):
            profile_id = self.path.split("/")[-1]
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA busy_timeout=5000;")
                cur = conn.cursor()
                cur.execute("SELECT desired_state, runtime_instance_id, observed_state FROM profile_runtimes WHERE profile_id=?", (profile_id,))
                row = cur.fetchone()
                if row:
                    res = {"profile_id": profile_id, "desired_state": row[0], "runtime_instance_id": row[1], "observed_state": row[2]}
                else:
                    res = {"profile_id": profile_id, "desired_state": "stopped", "runtime_instance_id": None, "observed_state": "stopped"}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if not self._check_auth():
            return
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode()
        data = json.loads(body) if body else {}

        if self.path == "/api/set-desired-state":
            profile_id = data["profile_id"]
            state = data["desired_state"]
            inst_id = data["runtime_instance_id"]
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA busy_timeout=5000;")
                conn.execute("""
                    INSERT INTO profile_runtimes (profile_id, desired_state, observed_state, runtime_instance_id)
                    VALUES (?, ?, 'stopped', ?)
                    ON CONFLICT(profile_id) DO UPDATE SET
                        desired_state=excluded.desired_state,
                        runtime_instance_id=excluded.runtime_instance_id;
                """, (profile_id, state, inst_id))
                conn.commit()
            log("API", f"Set desired_state for {profile_id}: {state} (inst={inst_id})")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')

        elif self.path == "/api/report-exit-event":
            if not isinstance(data, dict) or "event_id" not in data:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error": "invalid_event"}')
                return

            event = data
            event_id = event["event_id"]
            profile_id = event["profile_id"]
            event_inst_id = event["runtime_instance_id"]
            exit_code = event["exit_code"]

            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA busy_timeout=5000;")
                cur = conn.cursor()
                # 1. Deduplication
                cur.execute("SELECT 1 FROM processed_events WHERE event_id = ?", (event_id,))
                if cur.fetchone():
                    log("API", f"Deduplicated event {event_id} (already processed)")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status": "duplicate_ignored"}')
                    return

                # 2. Check current runtime_instance_id in DB
                cur.execute("SELECT runtime_instance_id, desired_state FROM profile_runtimes WHERE profile_id=?", (profile_id,))
                row = cur.fetchone()
                current_inst_id = row[0] if row else None
                if current_inst_id and current_inst_id != event_inst_id:
                    # Stale instance event rejection!
                    log("API", f"REJECTED stale exit event {event_id}: event_instance={event_inst_id} != db_current_instance={current_inst_id}")
                    conn.execute("INSERT INTO processed_events (event_id, profile_id, processed_at) VALUES (?, ?, datetime('now'));", (event_id, profile_id))
                    conn.commit()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"status": "stale_instance_rejected"}')
                    return

                # 3. Clean exit (0) -> desired_state=stopped, observed_state=stopped
                new_desired = "stopped" if exit_code == 0 else row[1] if row else "stopped"
                new_observed = "stopped" if exit_code == 0 else "failed"

                conn.execute("""
                    UPDATE profile_runtimes SET
                        desired_state = CASE WHEN ? = 0 THEN 'stopped' ELSE desired_state END,
                        observed_state = ?,
                        last_exit_event_id = ?
                    WHERE profile_id = ?;
                """, (exit_code, new_observed, event_id, profile_id))

                conn.execute("INSERT INTO processed_events (event_id, profile_id, processed_at) VALUES (?, ?, datetime('now'));", (event_id, profile_id))
                conn.commit()

            log("API", f"Processed exit event {event_id}: exit_code={exit_code} -> desired={new_desired}, observed={new_observed}")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "applied"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

def run_api_service(db_path, port, token):
    log("API", f"Initializing API SQLite DB at {db_path}...")
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profile_runtimes (
                profile_id TEXT PRIMARY KEY,
                desired_state TEXT NOT NULL,
                observed_state TEXT NOT NULL,
                runtime_instance_id TEXT,
                last_exit_event_id TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_events (
                event_id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                processed_at TEXT NOT NULL
            );
        """)
        conn.commit()

    ApiHttpHandler.db_path = db_path
    ApiHttpHandler.auth_token = token
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), ApiHttpHandler)
    log("API", f"API Service running on http://127.0.0.1:{port}")
    server.serve_forever()


# -------------------------------------------------------------
# ROLE: SUPERVISOR SERVICE (No SQLite mount, persistent event queue)
# -------------------------------------------------------------
class SupervisorService:
    def __init__(self, api_url, token, run_dir, profile_id, sigkill_before_drain=False):
        self.api_url = api_url
        self.token = token
        self.run_dir = run_dir
        self.profile_id = profile_id
        self.events_file = os.path.join(run_dir, "events.jsonl")
        self.uds_path = os.path.join(run_dir, "agent.sock")
        self.container_name = f"cbrowser-spike-recovery-runtime-{profile_id}"
        self.local_queue_file = os.path.join(run_dir, "supervisor_queue.jsonl")
        self.sigkill_before_drain = sigkill_before_drain
        self.reconcile_count = 0

    def append_events_to_queue_atomic(self, new_events):
        """Append events to queue using tmp file + fsync + replace (never truncate)"""
        existing = []
        if os.path.exists(self.local_queue_file):
            with open(self.local_queue_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        existing.append(json.loads(line))

        combined = existing + new_events
        tmp_path = self.local_queue_file + f".tmp.{os.getpid()}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            for ev in combined:
                f.write(json.dumps(ev) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.local_queue_file)

    def drain_events_to_api(self):
        """
        1. Safely transfer from events.jsonl to supervisor_queue.jsonl:
           First persist to queue, fsync, replace. ONLY THEN remove events.jsonl.
        2. Attempt sending queue items to API.
        """
        # Step 1: Ingest events from bind-mount directory
        if os.path.exists(self.events_file):
            ingest_events = []
            with open(self.events_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        ingest_events.append(json.loads(line))

            if ingest_events:
                # FIRST atomic write to queue
                self.append_events_to_queue_atomic(ingest_events)
                log("SUPERVISOR", f"Safely ingested {len(ingest_events)} event(s) to local queue file.")
                # ONLY THEN unlink source events.jsonl
                os.remove(self.events_file)

        # Checkpoint for testing SIGKILL crash recovery
        if self.sigkill_before_drain:
            log("SUPERVISOR", "[CHECKPOINT] Triggering self SIGKILL before sending queue to API...")
            os.kill(os.getpid(), signal.SIGKILL)

        # Step 2: Try sending local queue to API
        if not os.path.exists(self.local_queue_file):
            return True

        current_queue = []
        with open(self.local_queue_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    current_queue.append(json.loads(line))

        if not current_queue:
            return True

        remaining = []
        for ev in current_queue:
            try:
                req = urllib.request.Request(
                    f"{self.api_url}/api/report-exit-event",
                    data=json.dumps(ev).encode(),
                    headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    res = json.loads(resp.read().decode())
                    log("SUPERVISOR", f"Reported exit event {ev['event_id']} to API: {res}")
            except Exception as e:
                log("SUPERVISOR", f"API unreachable while reporting event {ev['event_id']}: {e}")
                remaining.append(ev)

        # Atomically write remaining events back
        tmp_path = self.local_queue_file + f".tmp.{os.getpid()}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            for ev in remaining:
                f.write(json.dumps(ev) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.local_queue_file)

        return len(remaining) == 0

    def fetch_desired_state(self):
        try:
            req = urllib.request.Request(
                f"{self.api_url}/api/desired-state/{self.profile_id}",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            log("SUPERVISOR", f"Failed to fetch desired_state from API: {e}")
            return None

    def is_container_running(self):
        try:
            out = subprocess.check_output(
                ["docker", "inspect", "-f", "{{.State.Running}}", self.container_name],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            return out == "true"
        except Exception:
            return False

    def reconcile_loop_step(self):
        self.reconcile_count += 1
        log("SUPERVISOR", f"--- Reconcile Step #{self.reconcile_count} ---")
        # Step A: Drain events to API
        drained = self.drain_events_to_api()
        if not drained:
            log("SUPERVISOR", "Persistent event queue not fully drained to API. Waiting before reconciliation.")
            return

        # Step B: Query desired state
        state_data = self.fetch_desired_state()
        if not state_data:
            log("SUPERVISOR", "API offline. Skipping reconciliation.")
            return

        desired = state_data["desired_state"]
        inst_id = state_data["runtime_instance_id"]
        is_running = self.is_container_running()
        log("SUPERVISOR", f"State: desired={desired}, container_running={is_running}, instance_id={inst_id}")

        if desired == "running" and not is_running:
            log("SUPERVISOR", f"Desired is running but container is stopped. Launching container {self.container_name}...")
            subprocess.run(["docker", "rm", "-f", self.container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            cmd = [
                "docker", "run", "-d",
                "--name", self.container_name,
                "--restart=no",  # STRICT: restart policy NO
                "--entrypoint", "python3",
                "-v", f"{self.run_dir}:/app_run",
                "cbrowser-spike-runtime-browser:test",
                "/app_run/container_agent.py", "/app_run", self.profile_id, inst_id
            ]
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log("SUPERVISOR", f"Container {self.container_name} started.")

        elif desired == "stopped" and is_running:
            log("SUPERVISOR", f"Desired is stopped but container is running. Stopping container {self.container_name}...")
            subprocess.run(["docker", "stop", "-t", "2", self.container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["docker", "rm", self.container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log("SUPERVISOR", f"Container {self.container_name} stopped and removed.")
        else:
            log("SUPERVISOR", "State in sync. No action needed.")


def run_supervisor_service(api_url, token, run_dir, profile_id, sigkill_before_drain=False):
    sup = SupervisorService(api_url, token, run_dir, profile_id, sigkill_before_drain=sigkill_before_drain)
    log("SUPERVISOR", f"Supervisor Service started for profile {profile_id}")
    while True:
        try:
            sup.reconcile_loop_step()
        except Exception as e:
            log("SUPERVISOR", f"Reconcile error: {e}")
        time.sleep(1.0)


# -------------------------------------------------------------
# MAIN ENTRYPOINT
# -------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=["api", "supervisor"], required=True)
    parser.add_argument("--db-path", default="")
    parser.add_argument("--port", type=int, default=58081)
    parser.add_argument("--api-url", default="http://127.0.0.1:58081")
    parser.add_argument("--token", required=True)
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--profile-id", default="prof_rec_1")
    parser.add_argument("--sigkill-before-drain", action="store_true")
    args = parser.parse_args()

    if args.role == "api":
        if not args.db_path:
            raise ValueError("--db-path required for api role")
        run_api_service(args.db_path, args.port, args.token)
    elif args.role == "supervisor":
        if not args.run_dir:
            raise ValueError("--run-dir required for supervisor role")
        run_supervisor_service(args.api_url, args.token, args.run_dir, args.profile_id, sigkill_before_drain=args.sigkill_before_drain)
