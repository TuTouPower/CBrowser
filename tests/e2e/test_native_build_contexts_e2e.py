"""Native BuildKit guards for the five runtime build-context allowlists."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.e2e_images()

_ALLOWED = {
    "api_runtime": "src/backend/cbrowser/__init__.py",
    "gateway_runtime": "src/backend/cbrowser/gateway/__init__.py",
    "supervisor_runtime": "src/backend/cbrowser/services/tunnel_registry.py",
    "browser_runtime": "src/backend/cbrowser/runtime_agent/__init__.py",
    "stream_runtime": "src/backend/cbrowser/stream_agent/__init__.py",
}


@pytest.mark.parametrize("runtime", _ALLOWED)
def test_native_runtime_context_enforces_leaf_allowlist(tmp_path: Path, runtime: str):
    allowed = _ALLOWED[runtime]
    requirements = f"config/docker/{runtime}/requirements.txt"
    package = str(Path(allowed).parent)
    forbidden = [
        f"{package}/__pycache__/probe.pyc",
        f"{package}/__pycache__/probe.py",
        f"{package}/probe.pyc",
        "config/deploy/secrets/private_fixture",
        "data/private_fixture",
    ]
    if runtime == "supervisor_runtime":
        forbidden.append("src/backend/cbrowser/services/profile_service.py")
    for name in [allowed, requirements, *forbidden]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic build-context input\n")
    dockerfile = tmp_path / "Dockerfile"
    (tmp_path / "Dockerfile.dockerignore").write_bytes(
        (ROOT / f"config/docker/{runtime}/Dockerfile.dockerignore").read_bytes()
    )

    def build(paths):
        dockerfile.write_text("FROM scratch\n" + "".join(f"COPY {path} /input_{index}\n" for index, path in enumerate(paths)))
        return subprocess.run(
            ["docker", "build", "--progress=plain", "-f", str(dockerfile), str(tmp_path)],
            capture_output=True, text=True, timeout=60, check=False,
        )

    positive = build([allowed, requirements])
    assert positive.returncode == 0, positive.stdout + positive.stderr
    for name in forbidden:
        negative = build([name])
        output = negative.stdout + negative.stderr
        assert negative.returncode != 0, f"{runtime} admitted forbidden input {name}"
        assert name in output and "not found" in output, output
