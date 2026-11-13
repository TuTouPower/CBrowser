"""t062: neutral-module and image-boundary structural guards.

These tests pin the architecture the refactor establishes, so a future
change cannot quietly reintroduce a cross-service dependency, a second
implementation of a shared rule, or a per-file Dockerfile exception:

- Gateway and Supervisor never import each other; shared rules live in
  ``cbrowser.shared`` exactly once, and ``shared`` imports no service
  package.
- Routes and auth dependencies consume the domain session object,
  never the ORM ``SessionModel``.
- ``domain.egress_observation`` carries no I/O implementation.
- The Supervisor control port has one authoritative value, and the
  CLI / runner / compose surfaces all agree with it.
- Runtime Dockerfiles copy the neutral package as a package; no image
  copies another service's package or individual shared files.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "src" / "backend" / "cbrowser"

SERVICE_PACKAGES = {
    "api",
    "auth",
    "services",
    "gateway",
    "supervisor",
    "adapters",
    "runtime_agent",
    "stream_agent",
    "agent_executor",
    "font_sets",
}


def _cbrowser_refs(py_file: Path) -> set[str]:
    """Top-level cbrowser package names referenced by any import.

    Relative imports are resolved against the file's own package, so a
    cross-service dependency cannot sneak past the guard as
    ``from ..supervisor import ...``.
    """
    refs: set[str] = set()
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    containing = ["cbrowser", *py_file.relative_to(BACKEND).parts[:-1]]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = containing[: len(containing) - node.level + 1]
                if node.module:
                    base = [*base, *node.module.split(".")]
                if len(base) > 1 and base[0] == "cbrowser":
                    refs.add(base[1])
                elif node.module is None and len(base) == 1:
                    refs.update(alias.name.split(".")[0] for alias in node.names)
            elif node.module == "cbrowser":
                refs.update(alias.name.split(".")[0] for alias in node.names)
            elif node.module and node.module.startswith("cbrowser."):
                refs.add(node.module.split(".")[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("cbrowser."):
                    refs.add(alias.name.split(".")[1])
    return refs


def _package_files(package: str) -> list[Path]:
    return sorted((BACKEND / package).rglob("*.py"))


def _imported_names(py_file: Path, module: str) -> set[str]:
    names: set[str] = set()
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            names.update(alias.name for alias in node.names)
    return names


def _defined_names(py_file: Path) -> set[str]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def test_gateway_and_supervisor_do_not_import_each_other() -> None:
    for py_file in _package_files("gateway"):
        assert "supervisor" not in _cbrowser_refs(py_file), py_file
    for py_file in _package_files("supervisor"):
        assert "gateway" not in _cbrowser_refs(py_file), py_file


def test_shared_imports_no_service_package() -> None:
    # The neutral package must be importable in every image that ships
    # it: its only cbrowser references are itself and the secret_files
    # leaf (which every shared-shipping image also ships).
    for py_file in _package_files("shared"):
        refs = _cbrowser_refs(py_file)
        assert not (refs & SERVICE_PACKAGES), (py_file, refs & SERVICE_PACKAGES)
        assert refs <= {"shared", "secret_files"}, (py_file, refs)


def test_shared_rules_defined_exactly_once() -> None:
    expectations = {
        "normalize_origin": BACKEND / "shared" / "endpoints.py",
        "GatewayEndpoint": BACKEND / "shared" / "endpoints.py",
        "AgentCredentials": BACKEND / "shared" / "agent_credentials.py",
        "atomic_write_text": BACKEND / "shared" / "atomic_write.py",
        "ProfileLockRegistry": BACKEND / "shared" / "profile_locks.py",
        "classify_delivery_status": BACKEND / "shared" / "delivery.py",
        "fence_by_instance": BACKEND / "shared" / "fencing.py",
    }
    for name, home in expectations.items():
        assert name in _defined_names(home), (name, home)
        for py_file in BACKEND.rglob("*.py"):
            if py_file == home or "__pycache__" in py_file.parts:
                continue
            assert name not in _defined_names(py_file), (name, py_file)


def test_old_cross_service_homes_are_gone() -> None:
    assert not (BACKEND / "gateway" / "endpoint.py").exists()
    assert not (BACKEND / "supervisor" / "agent_credentials.py").exists()
    assert not (BACKEND / "supervisor" / "file_storage.py").exists()


def test_routes_and_auth_dependencies_never_touch_orm_session() -> None:
    all_api_files = [BACKEND / "auth" / "dependencies.py"]
    all_api_files += sorted((BACKEND / "api" / "v1").glob("*.py"))
    for py_file in all_api_files:
        imported = _imported_names(py_file, "cbrowser.adapters.database.models")
        assert "SessionModel" not in imported, py_file
    session_consumers = [
        BACKEND / "auth" / "dependencies.py",
        BACKEND / "api" / "v1" / "artifact_router.py",
        BACKEND / "api" / "v1" / "auth_router.py",
        BACKEND / "api" / "v1" / "automation_router.py",
        BACKEND / "api" / "v1" / "control_router.py",
        BACKEND / "api" / "v1" / "preview_router.py",
        BACKEND / "api" / "v1" / "router.py",
    ]
    for py_file in session_consumers:
        assert "AuthenticatedSession" in _imported_names(
            py_file, "cbrowser.domain.models"
        ), py_file


def test_fence_call_sites_delegate_to_shared_rule() -> None:
    for rel in ("api/v1/runtime_views.py", "api/runtime_coordinator.py"):
        py_file = BACKEND / rel
        assert "fence_by_instance" in _imported_names(
            py_file, "cbrowser.shared.fencing"
        ), rel


def test_domain_egress_observation_has_no_io() -> None:
    py_file = BACKEND / "domain" / "egress_observation.py"
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module.split(".")[0])
    assert not (imported_modules & {"httpx", "os", "pathlib", "socket"})
    defined = _defined_names(py_file)
    assert not (
        defined & {"GeoIpLookup", "fetch_egress_ip", "probe_egress", "resolve_geoip_db_path"}
    )
    # The I/O implementation lives in the neutral shared package.
    shared_egress = BACKEND / "shared" / "egress.py"
    assert {"GeoIpLookup", "fetch_egress_ip", "probe_egress"} <= _defined_names(
        shared_egress
    )


def test_supervisor_port_single_authority() -> None:
    import inspect

    from cbrowser.shared.endpoints import DEFAULT_SUPERVISOR_PORT, DEFAULT_SUPERVISOR_URL
    from cbrowser.supervisor import control_client
    from cbrowser.supervisor.runner import run_supervisor

    assert DEFAULT_SUPERVISOR_URL == f"http://127.0.0.1:{DEFAULT_SUPERVISOR_PORT}"
    assert control_client.DEFAULT_SUPERVISOR_URL == DEFAULT_SUPERVISOR_URL
    # The runner's runtime default IS the authority value (not a copy).
    assert (
        inspect.signature(run_supervisor).parameters["port"].default
        == DEFAULT_SUPERVISOR_PORT
    )
    # The runner's CLI default references the constant, never a literal:
    # changing the constant must move the CLI default with it.
    runner_tree = ast.parse(
        (BACKEND / "supervisor" / "runner.py").read_text(encoding="utf-8")
    )
    cli_defaults = [
        keyword.value
        for node in ast.walk(runner_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_argument"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "--port"
        for keyword in node.keywords
        if keyword.arg == "default"
    ]
    assert len(cli_defaults) == 1
    assert isinstance(cli_defaults[0], ast.Name)
    assert cli_defaults[0].id == "DEFAULT_SUPERVISOR_PORT"
    # No divergent literals anywhere in the backend sources.
    for py_file in BACKEND.rglob("*.py"):
        if "__pycache__" in py_file.parts or py_file == (
            BACKEND / "shared" / "endpoints.py"
        ):
            continue
        text = py_file.read_text(encoding="utf-8")
        assert "8091" not in text, py_file
        assert "8005" not in text, py_file
    # Compose: every supervisor-facing port surface (service command,
    # in-container healthcheck URL, and other services' supervisor URLs)
    # agrees with the authority value.
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    block = re.search(
        r"^  supervisor:\n(.*?)(?=^  [a-z_]+:|\Z)", compose, re.MULTILINE | re.DOTALL
    )
    assert block is not None
    ports = set(re.findall(r'--port", "(\d+)"', block.group(1)))
    ports |= set(re.findall(r"127\.0\.0\.1:(\d+)", block.group(1)))
    ports |= set(re.findall(r"supervisor:(\d+)", compose))
    assert ports == {str(DEFAULT_SUPERVISOR_PORT)}, ports
    probe = (ROOT / "scripts" / "supervisor_readiness_probe.py").read_text(
        encoding="utf-8"
    )
    assert f"127.0.0.1:{DEFAULT_SUPERVISOR_PORT}" in probe


def test_dockerfiles_ship_shared_as_package_and_no_cross_service_copies() -> None:
    dockerfiles = {
        "api": ROOT / "config/docker/api_runtime/Dockerfile",
        "gateway": ROOT / "config/docker/gateway_runtime/Dockerfile",
        "supervisor": ROOT / "config/docker/supervisor_runtime/Dockerfile",
        "browser": ROOT / "config/docker/browser_runtime/Dockerfile",
        "stream": ROOT / "config/docker/stream_runtime/Dockerfile",
    }
    texts = {name: path.read_text(encoding="utf-8") for name, path in dockerfiles.items()}
    # No per-file copies out of the shared package anywhere.
    for name, text in texts.items():
        assert not re.search(r"COPY src/backend/cbrowser/shared/", text), name
        assert "cbrowser/shared" not in text or "cbrowser/shared " in text or (
            "cbrowser/shared\n" in text
        ), name
    # Every image that needs shared copies the whole package directory.
    for name in ("gateway", "supervisor", "browser"):
        assert re.search(
            r"^COPY src/backend/cbrowser/shared ", texts[name], re.MULTILINE
        ), name
    # No cross-service package copies between Gateway and Supervisor.
    assert "cbrowser/supervisor" not in texts["gateway"]
    assert "cbrowser/gateway" not in texts["supervisor"]
    # The API image copies by package, not the whole backend tree.
    assert not re.search(r"^COPY src/backend /app", texts["api"], re.MULTILINE)
    assert re.search(r"^COPY src/backend/cbrowser ", texts["api"], re.MULTILINE)
    assert re.search(r"^COPY src/backend/migrations ", texts["api"], re.MULTILINE)
