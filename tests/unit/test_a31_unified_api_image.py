"""A31: CBROWSER_API_TEST_IMAGE is delivered by the production API image.

The private supervisor_container_probe fixture duplicated the production
packaging with a hand-picked source subset and its own dockerignore.  The
production image (config/docker/api_runtime/Dockerfile, built by
deploy_v2.sh and verified by run_gates.sh) covers the same API role, so the
fixture, its ignore file, its text-only test and the stale guide entry are
removed together.  Live consumers of the image variable are kept.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROD_DOCKERFILE = REPO_ROOT / "config" / "docker" / "api_runtime" / "Dockerfile"
PROD_REQ = (
    REPO_ROOT / "config" / "docker" / "api_runtime" / "requirements.txt"
)
FIXTURE_DOCKERFILE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "supervisor_container_probe"
    / "api_runtime.Dockerfile"
)
FIXTURE_IGNORE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "supervisor_container_probe"
    / "api_runtime.Dockerfile.dockerignore"
)
GUIDE = REPO_ROOT / "docs" / "guides" / "supervisor_validation.md"
GATES = REPO_ROOT / "scripts" / "run_gates.sh"
DEPLOY = REPO_ROOT / "scripts" / "deploy_v2.sh"
E2E_ENV = REPO_ROOT / "tests" / "fixtures" / "e2e_env.py"
TOPOLOGY = REPO_ROOT / "tests" / "fixtures" / "gateway_probe" / "topology.py"
GRAPH_E2E = (
    REPO_ROOT / "tests" / "e2e" / "test_supervisor_container_graph_e2e.py"
)
BASELINE_TEST = (
    REPO_ROOT / "tests" / "unit" / "test_baseline_runtime_regressions.py"
)

FIXTURE_REF = "tests/fixtures/supervisor_container_probe/api_runtime.Dockerfile"


def _live_files() -> list[Path]:
    out = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=REPO_ROOT
    ).decode().split("\0")
    skip = (
        "docs/reviews/",
        "docs/archive/",
        "docs/tasks/",
        "docs/pending/",
        "docs/findings/",
        "docs/spikes/",
    )
    exts = {".py", ".sh", ".md", ".txt", ".yaml", ".yml", ".toml", ".json"}
    files = []
    for rel in out:
        if (
            not rel
            or rel.startswith(skip)
            or rel == "tests/unit/test_a31_unified_api_image.py"
        ):
            continue
        path = REPO_ROOT / rel
        if path.suffix in exts and path.is_file():
            files.append(path)
    return files


def test_private_fixture_and_ignore_removed() -> None:
    assert not FIXTURE_DOCKERFILE.exists()
    assert not FIXTURE_IGNORE.exists()


def test_no_live_reference_to_fixture_dockerfile() -> None:
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _live_files()
        if FIXTURE_REF in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == []


def test_text_only_fixture_test_removed() -> None:
    source = BASELINE_TEST.read_text(encoding="utf-8")
    assert "test_api_fixture_runtime_packaging_integrity" not in source
    assert FIXTURE_REF not in source
    assert "test_supervisor_runtime_packaging_integrity" in source
    assert "test_gateway_runtime_packaging_integrity" in source
    assert "test_stream_runtime_packaging_integrity" in source


def test_production_api_image_covers_fixture_runtime_role() -> None:
    dockerfile = PROD_DOCKERFILE.read_text(encoding="utf-8")
    assert "FROM python:3.15-slim-trixie@sha256:" in dockerfile
    assert "COPY src/backend /app" in dockerfile
    assert "EXPOSE 8000" in dockerfile
    assert "cbrowser.api.main:app" in dockerfile
    assert '--port", "8000"' in dockerfile
    assert "USER 1000:1000" in dockerfile

    requirements = PROD_REQ.read_text(encoding="utf-8")
    for package in (
        "fastapi==",
        "uvicorn==",
        "pydantic==",
        "httpx==",
        "sqlalchemy==",
        "alembic==",
        "aiosqlite==",
        "argon2-cffi==",
        "websockets==",
        "greenlet==",
    ):
        assert package in requirements


def test_deploy_builds_production_api_image() -> None:
    source = DEPLOY.read_text(encoding="utf-8")
    assert "-f config/docker/api_runtime/Dockerfile" in source


def test_gate_binds_api_test_image_to_production_requirements() -> None:
    source = GATES.read_text(encoding="utf-8")
    assert (
        "CBROWSER_API_TEST_IMAGE:config/docker/api_runtime/requirements.txt"
        in source
    )


def test_guide_points_to_production_entry_and_keeps_python_315() -> None:
    source = GUIDE.read_text(encoding="utf-8")
    assert "config/docker/api_runtime/Dockerfile" in source
    assert "supervisor_container_probe" not in source
    assert "API fixture" not in source
    assert "Python 3.15+" in source


def test_api_test_image_still_consumed_by_live_tests() -> None:
    for path in (E2E_ENV, TOPOLOGY, GRAPH_E2E):
        assert "CBROWSER_API_TEST_IMAGE" in path.read_text(encoding="utf-8")
    env_source = E2E_ENV.read_text(encoding="utf-8")
    assert "config/docker/api_runtime/Dockerfile" in env_source
