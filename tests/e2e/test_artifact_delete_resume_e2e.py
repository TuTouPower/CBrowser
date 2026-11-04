"""Artifact delete intent resumes across a real API process restart
(t028 AC-004).

Unit tests prove the resume logic with a fresh *service object*
(``test_artifact_service.py::test_pending_deletion_resumes_in_fresh_service``).
This entry proves the same contract across a real process boundary:
process 1 persists a deletion intent whose file removal fails, the
process exits, and process 2 — same database and artifacts root —
finishes the deletion during startup.  No Docker is required; the API
runs as a real uvicorn subprocess, mirroring the e2e conftest's
``real_api_server`` fixture env.
"""

from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from api_auth import create_auth_context

REPO_ROOT = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _ApiProcess:
    def __init__(self, work: Path, port: int) -> None:
        self.port = port
        self.url = f"http://127.0.0.1:{port}"
        self.log_path = work / f"api_{port}_{secrets.token_hex(3)}.log"
        self.proc: subprocess.Popen | None = None
        self._work = work

    def start(self, env: dict[str, str]) -> None:
        log_f = open(self.log_path, "w", encoding="utf-8")
        self._log_f = log_f
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "cbrowser.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            cwd=REPO_ROOT,
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 30
        with httpx.Client(base_url=self.url, trust_env=False) as client:
            while time.monotonic() < deadline:
                try:
                    if client.get("/api/v1/health").status_code == 200:
                        return
                except httpx.TransportError:
                    pass
                if self.proc.poll() is not None:
                    break
                time.sleep(0.1)
        raise AssertionError(
            f"API process did not become ready; log:\n"
            f"{self.log_path.read_text(encoding='utf-8', errors='replace')}"
        )

    def stop(self) -> None:
        if self.proc is None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
        self._log_f.close()
        self.proc = None


def _spawn_env(work: Path, db_path: Path, auth_env: dict[str, str]) -> dict[str, str]:
    env = dict(os.environ)
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        env.pop(name, None)
    token_file = work / "supervisor_token"
    if not token_file.exists():
        token_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        token_file.chmod(0o600)
    env.update(
        PYTHONPATH=str(REPO_ROOT / "src/backend"),
        PYTHONDONTWRITEBYTECODE="1",
        TMPDIR=str(work),
        CBROWSER_DB_PATH=str(db_path),
        CBROWSER_SUPERVISOR_TOKEN_FILE=str(token_file),
        **auth_env,
    )
    return env


def test_delete_intent_resumes_after_real_process_restart(
    tmp_path: Path,
) -> None:
    port = _free_port()
    origin = f"http://127.0.0.1:{port}"
    auth_ctx = create_auth_context(tmp_path / "auth", origin=origin)
    db_path = tmp_path / "control.db"
    artifacts_root = tmp_path / "artifacts"
    env = _spawn_env(tmp_path, db_path, auth_ctx.env)

    proc = _ApiProcess(tmp_path, port)
    payload = b"resume-me\n"
    try:
        proc.start(env)
        with httpx.Client(base_url=proc.url, trust_env=False) as client:
            headers = auth_ctx.login_sync(proc.url, client)
            created = client.post(
                "/api/v1/profiles", json={"name": "Resume"}, headers=headers
            )
            assert created.status_code == 201
            profile_id = created.json()["id"]
            uploaded = client.post(
                f"/api/v1/profiles/{profile_id}/artifacts",
                params={"filename": "resume.csv"},
                content=payload,
                headers={**headers, "Content-Type": "text/csv"},
            )
            assert uploaded.status_code == 201, uploaded.text
            artifact_id = uploaded.json()["id"]

            stored = [p for p in artifacts_root.rglob("*") if p.is_file()]
            assert len(stored) == 1
            artifact_file = stored[0]
            assert artifact_file.read_bytes() == payload

            # Make the file removal fail: a directory now occupies the
            # artifact's path, so unlink fails even for a privileged
            # process, while the deletion intent persists.
            held = artifact_file.with_name(artifact_file.name + ".held")
            artifact_file.rename(held)
            artifact_file.mkdir()
            deleted = client.request(
                "DELETE",
                f"/api/v1/profiles/{profile_id}/artifacts/{artifact_id}",
                headers=headers,
            )
            assert deleted.status_code == 500, deleted.text
        # The 500 above is a re-raised server error: uvicorn closes that
        # keep-alive connection after sending it, so the intent check
        # uses a fresh client (the headers carry the session cookie).
        with httpx.Client(base_url=proc.url, trust_env=False) as client:
            listed = client.get(
                f"/api/v1/profiles/{profile_id}/artifacts", headers=headers
            )
            assert [i["id"] for i in listed.json()] == [artifact_id]

        proc.stop()

        # Restore a deletable file at the recorded path, then restart:
        # startup resume must finish the persisted intent.
        artifact_file.rmdir()
        held.rename(artifact_file)

        proc.start(env)
        with httpx.Client(base_url=proc.url, trust_env=False) as client:
            headers = auth_ctx.login_sync(proc.url, client)
            deadline = time.monotonic() + 15
            status = None
            while time.monotonic() < deadline:
                resp = client.get(
                    f"/api/v1/profiles/{profile_id}/artifacts/{artifact_id}",
                    headers=headers,
                )
                status = resp.status_code
                if status == 404:
                    break
                time.sleep(0.2)
            assert status == 404
            listed = client.get(
                f"/api/v1/profiles/{profile_id}/artifacts", headers=headers
            )
            assert listed.json() == []
        assert not artifact_file.exists()
    finally:
        proc.stop()
