"""t034: runtime upgrade must not leave Python-minor-specific paths behind."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_selkies_asset_extraction_resolves_path_dynamically() -> None:
    for rel in (
        "tests/fixtures/gateway_probe/selkies_assets.py",
        "scripts/vendor_selkies_web.py",
    ):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "python3.12" not in text, f"{rel} still freezes the 3.12 path"
        assert 'exec_run(' in text, f"{rel} must discover the path in-image"
        assert '"find"' in text or "'find'" in text


def test_api_group_installs_sqlalchemy_asyncio_extra() -> None:
    pyproject = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    api = pyproject["dependency-groups"]["api"]
    assert any("sqlalchemy[asyncio]" in item for item in api), (
        "SQLAlchemy 2.1 asyncio requires greenlet; api group must use the "
        "asyncio extra"
    )
    requirements = (
        REPO_ROOT / "config" / "docker" / "api_runtime" / "requirements.txt"
    ).read_text(encoding="utf-8")
    assert "greenlet==" in requirements
