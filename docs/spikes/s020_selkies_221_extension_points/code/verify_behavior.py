#!/usr/bin/env python3
"""Spike behavioral check: patched selkies 2.2.1 vs current runtime wrappers.

Materializes ``_XTestKeyboard`` from the upstream wheel and from the
patched artifact as real modules (so the current production ABI check,
which reads ``__init__`` source, works), installs the *actual* current
``cbrowser.stream_agent.x11_keymap`` wrappers onto the upstream class,
and drives both implementations over an identical fake X display,
asserting identical observable outcomes for: spare-pool discovery (evdev
+ non-evdev), text_room, prebind capacity refusal, and prebind
keymap-reload + settle.  Also checks the ``__main__`` factory hook.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import subprocess as real_subprocess
import sys
import time
import types
import zipfile
from pathlib import Path

WHEEL = Path.home() / "workspace/CBrowser/.scratch/selkies_wheels/selkies-2.2.1-py3-none-any.whl"
PATCHED = Path("/tmp/spike_patches/selkies_input_handler.py.patched")
PATCHED_MAIN = Path("/tmp/spike_patches/selkies___main__.py.patched")
REPO_SRC = Path.home() / "workspace/CBrowser_t063/src/backend"
TMPMOD = Path("/tmp/spike_kb")
TEXT_SPARES = (*range(191, 203), 97, 132)

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
NAMED = {191, 192, 193, 210, 211}

HEADER = '''import os
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

'''


class FakeSubprocess:
    SubprocessError = real_subprocess.SubprocessError
    reload_calls: list = []

    @staticmethod
    def run(cmd, check=False, capture_output=False, timeout=None, input=None):
        if cmd[1] == "-xkb":
            return types.SimpleNamespace(stdout=CANNED_KEYMAP, returncode=0)
        FakeSubprocess.reload_calls.append((cmd, input))
        return types.SimpleNamespace(stdout=b"", returncode=0)


def segment(text: str, name: str) -> str:
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name == name:
            return "".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(f"{name} not found")


def load_module(mod_name: str, text: str, wanted: list[str]) -> types.ModuleType:
    TMPMOD.mkdir(parents=True, exist_ok=True)
    body = HEADER + "\n".join(segment(text, name) for name in wanted)
    path = TMPMOD / f"{mod_name}.py"
    path.write_text(body, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


class FakeDisplay:
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


def make_keyboard(cls, left_kc: int):
    kb = cls.__new__(cls)
    kb._d = FakeDisplay(left_kc)
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


def main() -> int:
    with zipfile.ZipFile(WHEEL) as z:
        upstream_text = z.read("selkies/input_handler.py").decode("utf-8")
    upstream_mod = load_module(
        "upstream_kb",
        upstream_text,
        ["keysym_to_character", "character_to_layout_keysym", "is_function_keysym", "overlay_bind_keysym", "_XTestKeyboard"],
    )
    UpstreamKeyboard = upstream_mod._XTestKeyboard

    fake_pkg = types.ModuleType("selkies")
    fake_ih = types.ModuleType("selkies.input_handler")
    fake_ih._XTestKeyboard = UpstreamKeyboard
    fake_pkg.input_handler = fake_ih
    sys.modules["selkies"] = fake_pkg
    sys.modules["selkies.input_handler"] = fake_ih
    sys.path.insert(0, str(REPO_SRC))
    os.environ.setdefault("DISPLAY", ":99")
    from cbrowser.stream_agent import x11_keymap

    x11_keymap.version = lambda name: "2.2.1"  # selkies not installed here
    x11_keymap._XKBCOMP = "/bin/true"
    x11_keymap._read_keymap = lambda: CANNED_KEYMAP
    x11_keymap.subprocess = FakeSubprocess
    x11_keymap.install_x11_keymap_refresh()

    patched_mod = load_module(
        "patched_kb",
        PATCHED.read_text(encoding="utf-8"),
        [
            "_read_xkb_keymap",
            "_xkb_named_keycodes",
            "_reload_xkb_keymap",
            "keysym_to_character",
            "character_to_layout_keysym",
            "is_function_keysym",
            "overlay_bind_keysym",
            "_XTestKeyboard",
        ],
    )
    PatchedKeyboard = patched_mod._XTestKeyboard

    real_sub = sys.modules["subprocess"]
    sys.modules["subprocess"] = FakeSubprocess
    try:
        for left_kc, label in ((113, "evdev"), (90, "non-evdev")):
            a = make_keyboard(UpstreamKeyboard, left_kc)
            b = make_keyboard(PatchedKeyboard, left_kc)
            pool_a = a._find_spare_keycodes()
            pool_b = b._find_spare_keycodes()
            assert pool_a == pool_b, (label, pool_a, pool_b)
            assert a._spare_set == b._spare_set and a._text_codes == b._text_codes, label
            assert pool_a and set(pool_a) <= NAMED, (label, pool_a)
            print(f"[{label}] spare pool identical: {pool_a} text_codes={a._text_codes}")

            a._pressed_kc = {0x61: pool_a[0]}
            b._pressed_kc = {0x61: pool_b[0]}
            assert a.text_room() == b.text_room(), (label, a.text_room(), b.text_room())
            print(f"[{label}] text_room identical: {a.text_room()}")

        overlays = {}
        for cls, tag in ((UpstreamKeyboard, "wrapped"), (PatchedKeyboard, "patched")):
            FakeSubprocess.reload_calls = []
            kb = make_keyboard(cls, 113)
            kb._find_spare_keycodes()
            before = time.monotonic()
            assert kb.prebind([0x4E00, 0x4E01]) is True, tag
            assert kb._settle_until >= before + 0.025 - 0.005, tag
            assert len(FakeSubprocess.reload_calls) == 1, (tag, FakeSubprocess.reload_calls)
            overlays[tag] = dict(kb._overlay)
            print(f"[{tag}] prebind ok overlay={sorted(kb._overlay)} reloads=1")
        assert overlays["wrapped"] == overlays["patched"], overlays
        print("prebind overlays identical; exactly one keymap reload on each side")

        for cls, tag in ((UpstreamKeyboard, "wrapped"), (PatchedKeyboard, "patched")):
            FakeSubprocess.reload_calls = []
            kb = make_keyboard(cls, 113)
            pool = kb._find_spare_keycodes()
            kb._pressed_kc = {0x61 + i: pool[i] for i in range(4)}
            assert kb.prebind([0x4E02, 0x4E03]) is False, tag
            assert kb._overlay == {} and not FakeSubprocess.reload_calls, tag
        print("prebind capacity refusal identical (False, no binds, no reload)")
    finally:
        sys.modules["subprocess"] = real_sub

    hook_mod = load_module("patched_main", PATCHED_MAIN.read_text(encoding="utf-8"), ["_webrtc_service"])
    import importlib as _importlib

    hook_mod.importlib = _importlib  # file-level import added by the patch itself
    hook_mod.os = os
    sentinel = object()
    hook_mod.WebRTCService = lambda server: ("stock", server)
    assert hook_mod._webrtc_service(sentinel) == ("stock", sentinel)
    os.environ["SELKIES_WEBRTC_SERVICE_FACTORY"] = "no-colon-here"
    try:
        hook_mod._webrtc_service(sentinel)
    except ValueError:
        print("__main__ hook: malformed factory ref raises ValueError")
    else:
        raise AssertionError("malformed factory ref must raise")
    os.environ["SELKIES_WEBRTC_SERVICE_FACTORY"] = "os.path:basename"
    assert hook_mod._webrtc_service("/a/b/c") == "c"
    del os.environ["SELKIES_WEBRTC_SERVICE_FACTORY"]
    print("__main__ hook: default + env override resolution verified")
    print("SPIKE BEHAVIOR: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
