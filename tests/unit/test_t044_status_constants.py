"""t044: guard the Starlette 1.10 422 status constant migration."""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "src" / "backend"
APP_PY = BACKEND_ROOT / "cbrowser" / "api" / "app.py"
ROUTER_PY = BACKEND_ROOT / "cbrowser" / "api" / "v1" / "router.py"

OLD_CONSTANT = "HTTP_422_UNPROCESSABLE_ENTITY"
NEW_CONSTANT = "HTTP_422_UNPROCESSABLE_CONTENT"


def _read(path: Path) -> str:
    assert path.is_file(), f"production source not found: {path}"
    return path.read_text(encoding="utf-8")


def test_deprecated_422_constant_absent_from_backend_sources():
    py_files = sorted(BACKEND_ROOT.rglob("*.py"))
    assert py_files, "no Python sources found under src/backend"
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in py_files
        if OLD_CONSTANT in _read(path)
    ]
    assert not offenders, (
        f"deprecated {OLD_CONSTANT} still referenced in: {offenders}"
    )


def test_app_and_router_use_new_422_constant():
    for path in (APP_PY, ROUTER_PY):
        content = _read(path)
        assert OLD_CONSTANT not in content, (
            f"{path.name} still references deprecated {OLD_CONSTANT}"
        )
        assert f"status.{NEW_CONSTANT}" in content, (
            f"{path.name} must use status.{NEW_CONSTANT}"
        )


def test_new_422_constant_value_is_422():
    try:
        from fastapi import status

        value = getattr(status, NEW_CONSTANT, None)
    except ImportError:
        value = None
    if value is None:
        pytest.skip(
            "fastapi exposing HTTP_422_UNPROCESSABLE_CONTENT is unavailable; "
            "source-level assertions still apply"
        )
    assert value == 422
