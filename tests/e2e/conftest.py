"""Shared E2E prerequisite and freshness gates."""

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
from e2e_env import REQUIRED_E2E_ENV

REPO_ROOT = Path(__file__).resolve().parents[2]



HOST_CHROME_PATH = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def _item_needs_host_chrome(item) -> bool:
    """True when the item's suite launches the host Google Chrome.

    Host-Chrome consumers drive Playwright with ``channel="chrome"`` (or the
    explicit CHROME_PATH constant); container-only suites (supervisor,
    browser runtime) never touch a host browser, so the Chrome prerequisite
    is scoped to the suites that actually need it (t024 AC-011/A33).
    """
    try:
        source = Path(str(item.fspath)).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return 'channel="chrome"' in source or "CHROME_PATH" in source


def _missing_requirements(items) -> list[str]:
    missing = [name for name in REQUIRED_E2E_ENV if not os.environ.get(name)]
    if any(_item_needs_host_chrome(item) for item in items) and not HOST_CHROME_PATH.is_file():
        missing.append("Google Chrome at /Applications")
    return missing


_DIST_CONSUMER_MARKERS = (
    "frontend_app_probe",
    "frontend_probe",
    "host_builder",
    "verify_frontend_build_freshness",
)


def _item_consumes_dist(item) -> bool:
    """True when the item's suite actually copies/serves the frontend dist
    (it drives one of the probe harnesses), regardless of the suite's
    filename (t024 AC-003/A24).  Suites that never touch dist do not gate
    on its freshness (t024 AC-011/A33: prerequisites stay scoped to what a
    suite actually needs)."""
    try:
        source = Path(str(item.fspath)).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return any(marker in source for marker in _DIST_CONSUMER_MARKERS)


def pytest_collection_modifyitems(config, items):
    # Freshness is enforced at collection for suites that consume dist,
    # and again at copy time inside the harnesses themselves.
    dist = REPO_ROOT / "src" / "frontend" / "dist"
    if items and dist.is_dir() and any(_item_consumes_dist(item) for item in items):
        from scripts.verify_frontend_dist import verify_frontend_build_freshness

        verify_frontend_build_freshness(
            dist,
            REPO_ROOT / "src" / "frontend",
        )

    if os.environ.get("CBROWSER_E2E_REQUIRED") != "1":
        return
    missing = _missing_requirements(items)
    if missing:
        details = "\n".join(f"- {name}: {REQUIRED_E2E_ENV.get(name, 'Google Chrome')}" for name in missing)
        pytest.exit(f"E2E required mode is missing prerequisites:\n{details}", returncode=2)


@pytest.fixture
def real_api_server(tmp_path: Path):
    """Real API subprocess fixture.

    Yields the four-tuple ``(api_url, auth_token, token_file, auth_headers)``
    (t024 AC-008/A29: consumers annotate all four elements).
    """
    token = secrets.token_urlsafe(32)
    token_file = tmp_path / "supervisor_token"
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    auth_ctx = create_auth_context(tmp_path, origin=f"http://127.0.0.1:{port}")
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

    root = Path(__file__).resolve().parents[2]
    env.update(
        PYTHONPATH=str(root / "src/backend"),
        PYTHONDONTWRITEBYTECODE="1",
        TMPDIR=str(tmp_path),
        CBROWSER_DB_PATH=str(tmp_path / "control.db"),
        CBROWSER_SUPERVISOR_TOKEN_FILE=str(token_file),
        **auth_ctx.env,
    )

    log_path = tmp_path / "api_server.log"
    with open(log_path, "w", encoding="utf-8") as log_f:
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "cbrowser.api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=root,
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
        )

        api_url = f"http://127.0.0.1:{port}"
        try:
            with httpx.Client(base_url=api_url, trust_env=False) as client:
                ready = False
                for _ in range(100):
                    try:
                        if client.get("/api/v1/health").status_code == 200:
                            ready = True
                            break
                    except httpx.TransportError:
                        pass
                    if proc.poll() is not None:
                        break
                    time.sleep(0.1)
                if not ready:
                    pytest.fail(
                        "Real API process failed to become ready: "
                        f"{log_path.read_text()}"
                    )
                auth_headers = auth_ctx.login_sync(api_url, client)
            yield api_url, token, token_file, auth_headers
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
