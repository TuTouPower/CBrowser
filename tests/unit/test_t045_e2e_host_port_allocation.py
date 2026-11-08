"""t045 AC-006: E2E host-port allocation guard.

A pinned host port inside a non-serial E2E module is a cross-worker
collision (``Bind ... port is already allocated``).  The shared gateway
harness must let the OS assign an ephemeral port instead of scanning a
fixed worker range (t044 AC-003 / t045 AC-006).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
E2E_DIR = REPO_ROOT / "tests" / "e2e"
HARNESS_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "gateway_probe" / "topology.py"
)

_SCAN_HELPERS = {"find_free_port", "_free_udp_port"}


def _module_is_serial(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "pytestmark"
                    and "serial" in ast.unparse(node.value)
                ):
                    return True
    return False


def _bind_zero(node: ast.Call) -> bool:
    if not (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "bind"
        and node.args
        and isinstance(node.args[0], ast.Tuple)
        and len(node.args[0].elts) == 2
    ):
        return False
    host = node.args[0].elts[1]
    return isinstance(host, ast.Constant) and host.value == 0


def _pinned_literal_ports(tree: ast.Module) -> list[int]:
    """Literal loopback ports pinned to a container ``ports=`` or ``bind``."""
    pinned: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "ports" and isinstance(kw.value, ast.Dict):
                for value in kw.value.values:
                    if isinstance(value, ast.Tuple) and len(value.elts) == 2:
                        host = value.elts[1]
                        if isinstance(host, ast.Constant) and isinstance(
                            host.value, int
                        ):
                            pinned.append(host.value)
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "bind"
            and node.args
            and isinstance(node.args[0], ast.Tuple)
            and len(node.args[0].elts) == 2
        ):
            host = node.args[0].elts[1]
            if (
                isinstance(host, ast.Constant)
                and isinstance(host.value, int)
                and host.value != 0
            ):
                pinned.append(host.value)
    return pinned


def _fixed_range_port_scans(tree: ast.Module) -> list[str]:
    """Calls that scan a fixed port range (``helper(start, end)``)."""
    calls: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _SCAN_HELPERS
            and node.args
        ):
            calls.append(ast.unparse(node))
    return calls


def _pinned_cli_port_mappings(tree: ast.Module) -> list[str]:
    """CLI ``-p 127.0.0.1:<host>:<container>`` with an explicit host port."""
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            text = "".join(
                part.value if isinstance(part, ast.Constant) else "{...}"
                for part in node.values
            )
            if "127.0.0.1:" in text and text.count("{...}") >= 2:
                hits.append(ast.unparse(node))
    return hits


def test_non_serial_e2e_modules_do_not_pin_host_ports() -> None:
    violations: list[str] = []
    for path in sorted(E2E_DIR.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if _module_is_serial(tree):
            continue
        for port in _pinned_literal_ports(tree):
            violations.append(f"{path.name}: pinned host port {port}")
        for call in _fixed_range_port_scans(tree):
            violations.append(f"{path.name}: fixed-range port scan {call}")
        for call in _pinned_cli_port_mappings(tree):
            violations.append(f"{path.name}: pinned CLI host port {call}")
    assert not violations, "\n".join(violations)


def test_shared_harness_ports_are_os_assigned() -> None:
    """The gateway harness must use bind(('127.0.0.1', 0)), not a fixed range."""
    source = HARNESS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "find_free_port"
        ),
        None,
    )
    assert fn is not None
    assert any(
        isinstance(node, ast.Call) and _bind_zero(node)
        for node in ast.walk(fn)
    ), "find_free_port must bind an OS-assigned ephemeral port (port 0)"
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "bind"
        and node.args
        and isinstance(node.args[0], ast.Tuple)
        and len(node.args[0].elts) == 2
        and not (
            isinstance(node.args[0].elts[1], ast.Constant)
            and node.args[0].elts[1].value == 0
        )
        for node in ast.walk(fn)
    ), "find_free_port must not bind a fixed host port"
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "CBROWSER_E2E_HTTP_BASE"
        for node in ast.walk(tree)
    ), "harness must not read the fixed HTTP worker base"
    assert not any(
        isinstance(node, ast.Name) and node.id == "http_base"
        for node in ast.walk(tree)
    )


def test_modules_with_pinned_host_ports_are_serial() -> None:
    """Any module that does pin a host port must be explicitly serial."""
    for path in sorted(E2E_DIR.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        pinned = (
            _pinned_literal_ports(tree)
            or _fixed_range_port_scans(tree)
            or _pinned_cli_port_mappings(tree)
        )
        if pinned:
            assert _module_is_serial(tree), (
                f"{path.name} pins a host port but is not marked serial"
            )
