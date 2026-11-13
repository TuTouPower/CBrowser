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
from e2e_env import worker_resource_offsets
from e2e_prerequisites import enforce_e2e_prerequisites

REPO_ROOT = Path(__file__).resolve().parents[2]

_PROXY_ENV = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def pytest_configure(config) -> None:
    """Partition per-worker resources and align the UDP mux range.

    ``worker_resource_offsets`` gives every xdist worker disjoint UDP/HTTP
    bases and a media subnet.  The xdist controller seeds the defaults
    first (no worker id), and workers inherit that environment; a plain
    ``setdefault`` would therefore leave every worker on the controller's
    base and collide on the host ports.  Workers must re-partition by
    *overwriting* the inherited values, while the controller still honours
    values the gate exported explicitly.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    for name, value in worker_resource_offsets().items():
        if worker:
            os.environ[name] = value
        else:
            os.environ.setdefault(name, value)
    base = os.environ["CBROWSER_E2E_UDP_BASE"]
    min_port, max_port = base, str(int(base) + 991)
    if worker:
        os.environ["CBROWSER_UDP_MUX_MIN_PORT"] = min_port
        os.environ["CBROWSER_UDP_MUX_MAX_PORT"] = max_port
    else:
        os.environ.setdefault("CBROWSER_UDP_MUX_MIN_PORT", min_port)
        os.environ.setdefault("CBROWSER_UDP_MUX_MAX_PORT", max_port)


@pytest.fixture(scope="session", autouse=True)
def _loopback_tests_ignore_proxy_environment():
    """The suite talks to loopback only; an inherited desktop proxy makes
    websockets/httpx route localhost through it (and break header APIs)."""
    for name in _PROXY_ENV:
        os.environ.pop(name, None)


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
    """Frontend-dist freshness gate (pure: reads no E2E session state).

    Enforced at collection for suites that consume dist, and again at copy
    time inside the harnesses themselves.  E2E required-mode prerequisites
    are a separate concern, enforced only in ``pytest_collection_finish`` so a
    non-E2E collection can never be affected by ``CBROWSER_E2E_REQUIRED``.
    """
    dist = REPO_ROOT / "src" / "frontend" / "dist"
    if items and dist.is_dir() and any(_item_consumes_dist(item) for item in items):
        from scripts.verify_frontend_dist import verify_frontend_build_freshness

        verify_frontend_build_freshness(
            dist,
            REPO_ROOT / "src" / "frontend",
        )


def pytest_collection_finish(session) -> None:
    """E2E-session prerequisite gate (t044 AC-005).

    This conftest is scoped to ``tests/e2e/``; the gate additionally verifies
    the collected content/config is an E2E session before enforcing, so a
    mixed/non-E2E collection can never be hijacked by the required-mode switch.
    """
    enforce_e2e_prerequisites(session.config, session.items)


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

    auth_ctx = create_auth_context(tmp_path)
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
