"""Shared integration fixtures."""

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


@pytest.fixture
def supervisor_api(tmp_path: Path):
    token = secrets.token_urlsafe(32)
    token_file = tmp_path / "supervisor_token"
    token_file.write_text(token)
    token_file.chmod(0o600)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    auth_ctx = create_auth_context(tmp_path, origin=f"http://127.0.0.1:{port}")
    env = dict(os.environ)
    for name in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        "http_proxy", "https_proxy", "all_proxy",
    ):
        env.pop(name, None)
    root = Path(__file__).resolve().parents[2]
    env.update(
        PYTHONPATH=str(root / "src/backend"),
        PYTHONDONTWRITEBYTECODE="1",
        TMPDIR=str(tmp_path),
        CBROWSER_DB_PATH=str(tmp_path / "control.db"),
        CBROWSER_SUPERVISOR_TOKEN_FILE=str(token_file),
        **auth_ctx.env,
    )
    with (tmp_path / "server.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "cbrowser.api.main:app",
             "--host", "127.0.0.1", "--port", str(port)],
            cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
                for _ in range(100):
                    try:
                        if client.get("/api/v1/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    if process.poll() is not None:
                        pytest.fail("isolated API process exited before readiness")
                    time.sleep(0.1)
                else:
                    pytest.fail("isolated API process did not become ready")
                auth_headers = auth_ctx.login_sync(f"http://127.0.0.1:{port}", client)
                client.headers.update(auth_headers)
                yield client, token
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
