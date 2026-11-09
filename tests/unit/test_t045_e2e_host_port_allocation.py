"""t045 AC-006: E2E host-port allocation guard.

A pinned host port inside a non-serial E2E module is a cross-worker
collision (``Bind ... port is already allocated``).  The gateway harness
publish is now daemon-allocated and read back (A28); this module keeps the
non-serial E2E pinned-port guard (t044 AC-003 / t045 AC-006).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
E2E_DIR = REPO_ROOT / "tests" / "e2e"

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
    """CLI ``-p 127.0.0.1:<host>:<container>`` with an explicit host port.

    Covers f-strings (``JoinedStr``) and ordinary strings (``Constant``).
    The daemon-allocated ``127.0.0.1::<container>`` / ``0.0.0.0::<container>``
    form (empty host) is safe and never flagged.
    """
    import re

    # Explicit host (digits or f-string placeholder), never empty (::).
    _host = r"(?:\d+|\{\.\.\.\})"
    _pinned_with_dash_p = re.compile(
        r"(?:127\.0\.0\.1|0\.0\.0\.0):(?!:)" + _host
    )
    # Without an in-string "-p" (flag split across argv list), require the
    # full host:container shape so plain URLs (single port, no second colon)
    # are not flagged.
    _pinned_bare = re.compile(
        r"(?:127\.0\.0\.1|0\.0\.0\.0):(?!:)" + _host + r":"
    )

    def _check_text(text: str) -> bool:
        if "127.0.0.1:" not in text and "0.0.0.0:" not in text:
            return False
        if "-p" in text:
            return bool(_pinned_with_dash_p.search(text))
        return bool(_pinned_bare.search(text))

    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            text = "".join(
                part.value if isinstance(part, ast.Constant) else "{...}"
                for part in node.values
            )
            if _check_text(text):
                hits.append(ast.unparse(node))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _check_text(node.value):
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


def test_pinned_cli_detects_plain_strings_and_daemon_allocated_is_safe() -> None:
    """Ordinary (non-f) strings with an explicit host are pinned; the
    daemon-allocated ``127.0.0.1::<container>`` form is safe."""
    pinned_plain = ast.parse(
        'cmd = "docker run -d -p 127.0.0.1:8080:80 img"\n'
    )
    assert _pinned_cli_port_mappings(pinned_plain), "plain string pinned missed"

    pinned_f = ast.parse(
        'cmd = f"docker run -d -p 127.0.0.1:{port}:80 img"\n'
    )
    assert _pinned_cli_port_mappings(pinned_f), "f-string pinned missed"

    bare_pinned = ast.parse('x = f"127.0.0.1:{host}:{container}"\n')
    assert _pinned_cli_port_mappings(bare_pinned), "bare host:container missed"

    safe_daemon = ast.parse('x = f"127.0.0.1::{port}"\n')
    assert not _pinned_cli_port_mappings(safe_daemon), "daemon :: flagged"

    safe_plain_daemon = ast.parse('x = "127.0.0.1::8080"\n')
    assert not _pinned_cli_port_mappings(safe_plain_daemon), "plain :: flagged"

    safe_url = ast.parse('url = f"http://127.0.0.1:{port}"\n')
    assert not _pinned_cli_port_mappings(safe_url), "dynamic URL flagged"
