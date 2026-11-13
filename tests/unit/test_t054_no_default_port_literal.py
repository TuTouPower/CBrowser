"""t054 AC-005: the default HTTPS port is defined in exactly one place.

``DEFAULT_HTTPS_PORT`` in ``cbrowser/network_config.py`` is the single
definition; every other place (deploy.sh, the API entrypoint, the
frontend) must obtain the port from the deployment environment or import
that constant. ``.env.example`` and docs carry example values, not
definitions, and are out of scope for this scan.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCAN_GLOBS = (
    ("src/backend", "*.py"),
    ("src/frontend/src", "*.ts"),
    ("src/frontend/src", "*.tsx"),
    ("scripts", "*.sh"),
)
SCAN_FILES = ("compose.yaml",)


def _scan() -> list[str]:
    hits: list[str] = []
    for base, pattern in SCAN_GLOBS:
        for path in (ROOT / base).rglob(pattern):
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if "56661" in line:
                    hits.append(f"{path.relative_to(ROOT)}:{number}:{line.strip()}")
    for name in SCAN_FILES:
        path = ROOT / name
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if "56661" in line:
                hits.append(f"{path.relative_to(ROOT)}:{number}:{line.strip()}")
    return hits


def test_default_https_port_literal_appears_exactly_once() -> None:
    hits = _scan()
    assert len(hits) == 1, hits
    path, _, line = hits[0].split(":", 2)
    assert path == "src/backend/cbrowser/network_config.py", hits
    assert line.strip() == "DEFAULT_HTTPS_PORT = 56661", hits
