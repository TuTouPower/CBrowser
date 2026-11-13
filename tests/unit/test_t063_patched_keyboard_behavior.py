"""t063: behavior shipped inside the controlled Selkies build.

These tests execute the keyboard and service-hook code *from the built
controlled wheel* (not from a copied fixture), so the artifact that the
image installs is the artifact whose behavior is verified: named-spare
filtering, text_room whole-pool fallback, prebind capacity protection
with post-bind keymap reload/settle, the WebRTC service factory hook,
and the fail-loud policy factory seam.  AC-004 static guards live here
too: startup must not parse upstream sources or replace upstream
attributes at runtime.
"""

from __future__ import annotations

import json
import os
import subprocess as real_subprocess
import sys
import types
import zipfile
from pathlib import Path

import pytest

from scripts import build_selkies_controlled as build_module
from scripts import vendor_selkies_web as vendor_module

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "config" / "selkies" / "selkies_controlled_build.json"
PATCHES_DIR = REPO_ROOT / "config" / "selkies" / "patches"
WHEEL_CACHE = Path(
    os.environ.get(
        "CBROWSER_SELKIES_WHEEL_CACHE", str(REPO_ROOT / ".scratch" / "selkies_wheels")
    )
)


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    source = WHEEL_CACHE / vendor_module.PINNED_WHEEL_FILENAME
    assert source.is_file(), f"local Selkies wheel cache missing: {source}"
    out = tmp_path_factory.mktemp("controlled") / manifest["controlled"]["wheel_filename"]
    build_module.build_controlled_wheel(source, PATCHES_DIR, manifest, out)
    return out


def _wheel_text(built_wheel: Path, name: str) -> str:
    with zipfile.ZipFile(built_wheel) as z:
        return z.read(name).decode("utf-8")

# ---------------------------------------------------------------------------
# Fake X environment (mirrors spike s020's verified equivalence harness)
# ---------------------------------------------------------------------------

CANNED_KEYMAP = b"""xkb_keymap {
    xkb_keycodes {
        <I191> = 191;
        <I192> = 192;
        <I193> = 193;
        <I210> = 210;
        <I211> = 211;
    };
};
"""

_MODULE_HEADER = """import os
import re
import time
from typing import Any, Iterable, List, Optional


class _WaylandKeymapOwner:
    _TEXT_SPARES = (*range(191, 203), 97, 132)


def open_xkb_link(display):
    return None


_XKBCOMP_PATH = "/usr/bin/xkbcomp"
libxkb = None
XK = None

"""


class _FakeSubprocess:
    """sys.modules['subprocess'] stand-in: dump vs reload by argv shape."""

    SubprocessError = real_subprocess.SubprocessError
    reload_calls: list = []

    @staticmethod
    def run(cmd, check=False, capture_output=False, timeout=None, input=None):
        if len(cmd) > 1 and cmd[1] == "-xkb":
            return types.SimpleNamespace(stdout=CANNED_KEYMAP, returncode=0)
        _FakeSubprocess.reload_calls.append((cmd, input))
        return types.SimpleNamespace(stdout=b"", returncode=0)


class _FakeDisplay:
    def __init__(self, left_kc: int):
        self.left_kc = left_kc
        self.display = types.SimpleNamespace(
            info=types.SimpleNamespace(min_keycode=8, max_keycode=255)
        )
        self.mapping: dict[int, list[int]] = {}
        for kc in range(8, 256):
            self.mapping[kc] = [0x1000 + kc]
        for kc in (191, 192, 193, 194, 210, 211, 212):
            self.mapping[kc] = [0, 0, 0, 0]
        self.changed: list = []

    def get_keyboard_mapping(self, lo, count):
        return [list(self.mapping[lo + i]) for i in range(count)]

    def get_modifier_mapping(self):
        return [[0] * 8 for _ in range(8)]

    def keysym_to_keycode(self, keysym):
        if keysym == 0xFF51:
            return self.left_kc
        for kc, syms in self.mapping.items():
            if keysym in syms:
                return kc
        return 0

    def change_keyboard_mapping(self, first_kc, rows):
        self.changed.append((first_kc, [list(r) for r in rows]))
        for i, row in enumerate(rows):
            self.mapping[first_kc + i] = list(row)

    def keycode_to_keysym(self, kc, index):
        syms = self.mapping.get(kc, [0])
        return syms[index] if index < len(syms) else 0

    def sync(self):
        pass


def _segment(text: str, name: str) -> str:
    import ast as _ast

    text_lines = text.splitlines(keepends=True)
    tree = _ast.parse(text)
    for node in tree.body:
        if isinstance(node, (_ast.ClassDef, _ast.FunctionDef)) and node.name == name:
            return "".join(text_lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"{name} not found in built input_handler.py")


@pytest.fixture(scope="module")
def keyboard_module(built_wheel: Path, tmp_path_factory: pytest.TempPathFactory):
    """Materialize the built wheel's keyboard code as a real module."""
    import importlib.util

    text = _wheel_text(built_wheel, "selkies/input_handler.py")
    wanted = [
        "_read_xkb_keymap",
        "_xkb_named_keycodes",
        "_reload_xkb_keymap",
        "keysym_to_character",
        "character_to_layout_keysym",
        "is_function_keysym",
        "overlay_bind_keysym",
        "_XTestKeyboard",
    ]
    body = _MODULE_HEADER + "\n".join(_segment(text, name) for name in wanted)
    mod_dir = tmp_path_factory.mktemp("built_kb")
    mod_path = mod_dir / "built_kb.py"
    mod_path.write_text(body, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("built_kb", mod_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["built_kb"] = module
    spec.loader.exec_module(module)
    return module


def _make_keyboard(module, left_kc: int, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.setitem(sys.modules, "subprocess", _FakeSubprocess)
    _FakeSubprocess.reload_calls = []
    kb = module._XTestKeyboard.__new__(module._XTestKeyboard)
    kb._d = _FakeDisplay(left_kc)
    kb._xkb = None
    kb._group_hold = None
    kb._group_restore = None
    kb._shift_kc = 0
    kb._shift_r_kc = 0
    kb._altgr_kc = 0
    kb._effective_mod_keycodes = set()
    kb._synth_mods = {}
    kb._spare_keycodes = None
    kb._spare_set = frozenset()
    kb._text_codes = 0
    kb._overlay = {}
    kb._overlay_value_kc = {}
    kb._settle_until = 0.0
    kb._overlay_order = []
    kb._pressed_kc = {}
    return kb


# ---------------------------------------------------------------------------
# Keyboard behavior inside the artifact
# ---------------------------------------------------------------------------


def test_built_keyboard_filters_spares_to_named_keycodes(
    keyboard_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Display offers spares 191-194/210-212; the canned server keymap only
    # names 191, 192, 193, 210, 211, so 194/212 must be filtered out.
    evdev = _make_keyboard(keyboard_module, 113, monkeypatch)
    assert evdev._find_spare_keycodes() == [191, 192, 193, 210, 211]
    assert evdev._text_codes == 0  # evdev layout: no text prefix
    xorg = _make_keyboard(keyboard_module, 90, monkeypatch)
    assert xorg._find_spare_keycodes() == [191, 192, 193, 210, 211]
    assert xorg._text_codes == 3  # non-evdev: 191, 192, 193 form the prefix


def test_built_keyboard_text_room_falls_back_to_whole_pool(
    keyboard_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    evdev = _make_keyboard(keyboard_module, 113, monkeypatch)
    pool = evdev._find_spare_keycodes()
    evdev._pressed_kc = {0x61: pool[0]}
    # Text prefix is empty on evdev; the whole-pool free count is 4.
    assert evdev.text_room() == 4
    xorg = _make_keyboard(keyboard_module, 90, monkeypatch)
    pool = xorg._find_spare_keycodes()
    xorg._pressed_kc = {0x61: pool[0]}
    assert xorg.text_room() == 2  # 3 text codes, one pressed


def test_built_keyboard_prebind_reloads_keymap_once_and_settles(
    keyboard_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time as _time

    kb = _make_keyboard(keyboard_module, 113, monkeypatch)
    kb._find_spare_keycodes()
    before = _time.monotonic()
    assert kb.prebind([0x4E00, 0x4E01]) is True
    assert sorted(kb._overlay) == [0x4E00, 0x4E01]
    assert sorted(kb._overlay.values()) == [191, 192]
    assert len(_FakeSubprocess.reload_calls) == 1
    assert kb._settle_until >= before + 0.02


def test_built_keyboard_prebind_respects_capacity_under_held_keys(
    keyboard_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    kb = _make_keyboard(keyboard_module, 113, monkeypatch)
    pool = kb._find_spare_keycodes()
    kb._pressed_kc = {0x61 + i: pool[i] for i in range(4)}
    assert kb.prebind([0x4E02, 0x4E03]) is False
    assert kb._overlay == {}
    assert _FakeSubprocess.reload_calls == []


def test_built_keymap_query_without_display_fails_with_safe_message(
    keyboard_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DISPLAY", raising=False)
    with pytest.raises(RuntimeError, match="X11 keyboard map query failed"):
        keyboard_module._read_xkb_keymap()


def test_built_keyboard_real_init_provides_every_attribute(
    keyboard_module, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Construct through the real __init__ (not __new__ + hand-filled state).

    The deleted ABI gate asserted the upstream __init__ initializes the
    instance attributes the keyboard methods depend on; for the owned
    controlled build that coverage now lives here, against the artifact.
    """
    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.setitem(sys.modules, "subprocess", _FakeSubprocess)
    keyboard = keyboard_module._XTestKeyboard(_FakeDisplay(113))
    assert keyboard._d is not None
    assert keyboard._xkb is None  # HEADER stub open_xkb_link returns None
    assert keyboard._group_hold is None
    assert keyboard._group_restore is None
    assert keyboard._shift_kc == 0  # FakeDisplay maps no shift keysym
    assert keyboard._shift_r_kc == 0
    assert keyboard._altgr_kc == 0
    assert keyboard._effective_mod_keycodes == set()
    assert keyboard._synth_mods == {}
    assert keyboard._spare_keycodes is None
    assert keyboard._spare_set == frozenset()
    assert keyboard._text_codes == 0
    assert keyboard._overlay == {}
    assert keyboard._overlay_value_kc == {}
    assert keyboard._settle_until == 0.0
    assert keyboard._overlay_order == []
    assert keyboard._pressed_kc == {}
    # And the really-constructed instance discovers the named pool itself.
    assert keyboard._find_spare_keycodes() == [191, 192, 193, 210, 211]


# ---------------------------------------------------------------------------
# Service factory hook inside the artifact
# ---------------------------------------------------------------------------


def _materialize_hook(built_wheel: Path) -> types.SimpleNamespace:
    text = _wheel_text(built_wheel, "selkies/__main__.py")
    start = text.index("def _webrtc_service")
    end = text.index("async def run()", start)
    namespace: dict = {"os": os, "importlib": __import__("importlib")}

    class StockService:
        def __init__(self, server) -> None:
            self.server = server

    namespace["WebRTCService"] = StockService
    exec(compile(text[start:end], "built_main_hook", "exec"), namespace)
    return types.SimpleNamespace(**namespace)


def test_built_hook_defaults_to_stock_service(
    built_wheel: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hook = _materialize_hook(built_wheel)
    monkeypatch.delenv("SELKIES_WEBRTC_SERVICE_FACTORY", raising=False)
    service = hook._webrtc_service("server-1")
    assert type(service).__name__ == "StockService"
    assert service.server == "server-1"


def test_built_hook_resolves_named_factory(
    built_wheel: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hook = _materialize_hook(built_wheel)
    monkeypatch.setenv(
        "SELKIES_WEBRTC_SERVICE_FACTORY",
        "cbrowser.stream_agent.policy:create_policy_service",
    )
    sentinel = object()
    seen: list = []

    def fake_factory(server):
        seen.append(server)
        return sentinel

    import cbrowser.stream_agent.policy as policy_module

    monkeypatch.setattr(policy_module, "create_policy_service", fake_factory)
    assert hook._webrtc_service("server-2") is sentinel
    assert seen == ["server-2"]


def test_built_hook_rejects_malformed_factory_reference(
    built_wheel: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hook = _materialize_hook(built_wheel)
    monkeypatch.setenv("SELKIES_WEBRTC_SERVICE_FACTORY", "no-colon-here")
    with pytest.raises(ValueError, match="module:attribute"):
        hook._webrtc_service("server-3")


def test_built_main_registers_service_through_the_hook(built_wheel: Path) -> None:
    """The registration line is the hook's only runtime integration seam."""
    text = _wheel_text(built_wheel, "selkies/__main__.py")
    assert text.count('server.register_service("webrtc", _webrtc_service(server))') == 1
    assert 'server.register_service("webrtc", WebRTCService(server))' not in text


# ---------------------------------------------------------------------------
# Startup seam in our own code (AC-004)
# ---------------------------------------------------------------------------


def test_policy_factory_seam_fails_loud_until_bound() -> None:
    import cbrowser.stream_agent.policy as policy_module

    original = policy_module._webrtc_service_factory
    try:
        policy_module._webrtc_service_factory = None
        with pytest.raises(RuntimeError, match="not bound"):
            policy_module.create_policy_service(object())
        marker = object()
        policy_module.bind_webrtc_service_factory(lambda server: (server, marker))
        server = object()
        assert policy_module.create_policy_service(server) == (server, marker)
    finally:
        policy_module._webrtc_service_factory = original


def test_controlled_build_startup_verification(tmp_path: Path) -> None:
    """agent startup refuses a stock Selkies install (no build stamp)."""
    from cbrowser.stream_agent.agent import verify_controlled_selkies_build

    package = tmp_path / "selkies"
    package.mkdir()
    init = package / "__init__.py"
    init.write_text("", encoding="utf-8")
    with pytest.raises(RuntimeError, match="stamp missing"):
        verify_controlled_selkies_build(init, installed_version="2.2.1")
    stamp = {
        "controlled_version": "2.2.1+cbrowser.1",
        "upstream": {"wheel_sha256": "a" * 64},
    }
    (package / "cbrowser_build.json").write_text(json.dumps(stamp), encoding="utf-8")
    with pytest.raises(RuntimeError, match="!="):
        verify_controlled_selkies_build(init, installed_version="2.2.1")
    assert (
        verify_controlled_selkies_build(init, installed_version="2.2.1+cbrowser.1")
        == stamp
    )


def test_startup_has_no_runtime_patch_or_upstream_source_parsing() -> None:
    import ast as _ast

    agent_source = (
        REPO_ROOT / "src/backend/cbrowser/stream_agent/agent.py"
    ).read_text(encoding="utf-8")
    assert "selkies_main.WebRTCService =" not in agent_source
    assert "install_x11_keymap_refresh" not in agent_source
    assert "SELKIES_WEBRTC_SERVICE_FACTORY" in agent_source
    src_root = REPO_ROOT / "src"
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in src_root.rglob("*.py")
        if "getsource(" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
    assert not (src_root / "backend/cbrowser/stream_agent/x11_keymap.py").exists()

    # AST-level guard over the whole stream_agent package: no assignment
    # to an attribute of a selkies-rooted name (any spelling, including
    # setattr), no inspect import, and no private-ABI gate symbols.
    package = src_root / "backend/cbrowser/stream_agent"
    violations: list[str] = []
    for path in sorted(package.rglob("*.py")):
        tree = _ast.parse(path.read_text(encoding="utf-8"))
        for node in _ast.walk(tree):
            where = f"{path.name}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, _ast.Import):
                if any(alias.name == "inspect" for alias in node.names):
                    violations.append(f"{where}: inspect import")
            elif isinstance(node, _ast.ImportFrom):
                if node.module == "inspect":
                    violations.append(f"{where}: inspect import")
            elif isinstance(node, (_ast.Assign, _ast.AugAssign, _ast.AnnAssign)):
                targets = node.targets if isinstance(node, _ast.Assign) else [node.target]
                for target in targets:
                    # A module-attribute write is exactly one Attribute
                    # level on the module name (selkies_main.WebRTCService);
                    # deeper chains and plain locals are instance state.
                    if (
                        isinstance(target, _ast.Attribute)
                        and isinstance(target.value, _ast.Name)
                        and "selkies" in target.value.id
                    ):
                        violations.append(f"{where}: assignment to selkies attribute")
            elif isinstance(node, _ast.Call):
                func = node.func
                if isinstance(func, _ast.Name) and func.id == "setattr" and node.args:
                    first = node.args[0]
                    if isinstance(first, _ast.Name) and "selkies" in first.id:
                        violations.append(f"{where}: setattr on selkies module")
                    elif (
                        isinstance(first, _ast.Attribute)
                        and isinstance(first.value, _ast.Name)
                        and "selkies" in first.value.id
                    ):
                        violations.append(f"{where}: setattr on selkies module")
            elif isinstance(node, _ast.Name) and node.id == "SUPPORTED_SELKIES_VERSION":
                violations.append(f"{where}: ABI version gate symbol")
            elif isinstance(node, _ast.Constant) and isinstance(node.value, str):
                if "SUPPORTED_SELKIES_VERSION" in node.value:
                    violations.append(f"{where}: ABI version gate symbol")
    assert violations == []
