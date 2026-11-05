"""Keep native Selkies text overlays coherent with Chromium's XKB cache.

An active Chromium can retain its old map after core symbol changes. Reloading
that map broadcasts a keyboard replacement, provided every spare has an XKB
name: unnamed keys coalesce during serialization. Input remains native XTest.
"""

import ast
import inspect
import os
import re
import subprocess
import textwrap
import time
from importlib.metadata import version
from pathlib import Path

_installed = False
_XKBCOMP = "/usr/bin/xkbcomp"


def _read_keymap() -> bytes:
    try:
        return subprocess.run(
            [_XKBCOMP, "-xkb", os.environ["DISPLAY"], "-"],
            check=True,
            capture_output=True,
            timeout=2,
        ).stdout
    except (OSError, subprocess.SubprocessError, KeyError):
        # Keyboard maps contain private text symbols; never attach child output.
        raise RuntimeError("X11 keyboard map query failed") from None


# The complete Selkies private surface this adapter depends on (verified
# against the pinned selkies==2.1.0 wheel in the t022 A47 spike and
# re-verified for 2.2.1 in the t043 s012 spike). Any drift must surface as
# an explicit unsupported-ABI failure at install time, never as an
# AttributeError deep in input handling that looks like a dead driver.
SUPPORTED_SELKIES_VERSION = "2.2.1"
_ABI_METHODS = (
    ("prebind", ["self", "keysyms"]),
    ("text_room", ["self"]),
    ("_find_spare_keycodes", ["self"]),
    ("_layout_keycode", ["self", "keysym"]),
)
_ABI_INSTANCE_ATTRIBUTES = (
    "_spare_keycodes",
    "_spare_set",
    "_text_codes",
    "_overlay",
    "_pressed_kc",
    "_settle_until",
)


def _init_assigned_attributes(keyboard_cls: type) -> set[str]:
    """Attribute names assigned as self.<attr> anywhere in __init__'s AST.

    AST-based rather than substring matching: comments or string literals
    mentioning an attribute must not pass the check, and formatting must
    not fail it (review t022_code_f009).
    """
    try:
        init_source = inspect.getsource(keyboard_cls.__init__)
        tree = ast.parse(textwrap.dedent(init_source))
    except (OSError, TypeError, SyntaxError):
        raise RuntimeError(
            "Unsupported Selkies text binding ABI: __init__ unreadable"
        ) from None
    assigned: set[str] = set()
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                assigned.add(target.attr)
    return assigned


def _verify_selkies_keyboard_abi(keyboard_cls: type) -> None:
    """Fail loudly unless the SDK keyboard class matches the pinned ABI."""
    for name, parameters in _ABI_METHODS:
        method = getattr(keyboard_cls, name, None)
        try:
            signature_ok = callable(method) and list(
                inspect.signature(method).parameters
            ) == parameters
        except (TypeError, ValueError):
            # Callables without an introspectable signature cannot be
            # verified against the pinned ABI: report unsupported, do not
            # leak a bare introspection error (review t022_code_f009).
            signature_ok = False
        if not signature_ok:
            raise RuntimeError(
                f"Unsupported Selkies text binding ABI: method {name}"
            )
    settle = getattr(keyboard_cls, "_BIND_SETTLE_S", None)
    if not isinstance(settle, (int, float)) or isinstance(settle, bool) or settle <= 0:
        raise RuntimeError(
            "Unsupported Selkies text binding ABI: _BIND_SETTLE_S"
        )
    assigned = _init_assigned_attributes(keyboard_cls)
    for attribute in _ABI_INSTANCE_ATTRIBUTES:
        if attribute not in assigned:
            raise RuntimeError(
                f"Unsupported Selkies text binding ABI: attribute {attribute}"
            )


def install_x11_keymap_refresh() -> None:
    """Install the version-bound adapter before the native input handler starts."""
    global _installed
    if _installed:
        return
    if version("selkies") != SUPPORTED_SELKIES_VERSION or not Path(_XKBCOMP).is_file():
        raise RuntimeError(
            f"Unsupported X11 input runtime: requires selkies=={SUPPORTED_SELKIES_VERSION}"
        )

    from selkies.input_handler import _XTestKeyboard

    _verify_selkies_keyboard_abi(_XTestKeyboard)
    original = _XTestKeyboard.prebind
    original_room = _XTestKeyboard.text_room
    original_spares = _XTestKeyboard._find_spare_keycodes

    def find_named_spares(keyboard):
        codes = original_spares(keyboard)
        preferred = set(codes[: keyboard._text_codes])
        named = {
            int(match.group(1))
            for match in re.finditer(
                rb"^\s*<[^>]+>\s*=\s*(\d+);", _read_keymap(), re.MULTILINE
            )
        }
        if not named:
            raise RuntimeError("X11 keyboard names unavailable")
        codes = [code for code in codes if code in named]
        keyboard._spare_set = frozenset(codes)
        keyboard._text_codes = sum(code in preferred for code in codes)
        return codes

    def text_room(keyboard):
        room = original_room(keyboard)
        if room:
            return room
        # Native evdev returns zero (unbounded), but prebind has a finite pool.
        if keyboard._spare_keycodes is None:
            # Mirror the SDK's own consumers: initialize the same finite
            # pool on first use instead of treating None as unbounded.
            keyboard._spare_keycodes = keyboard._find_spare_keycodes()
        held = set(keyboard._pressed_kc.values())
        return sum(key not in held for key in keyboard._spare_keycodes)

    def prebind_with_refresh(keyboard, keysyms):
        keysyms = tuple(dict.fromkeys(keysyms))
        missing = [
            symbol
            for symbol in keysyms
            if symbol not in keyboard._overlay and not keyboard._layout_keycode(symbol)
        ]
        if missing:
            if keyboard._spare_keycodes is None:
                keyboard._spare_keycodes = keyboard._find_spare_keycodes()
            protected = set(keyboard._pressed_kc.values())
            protected.update(
                keyboard._overlay[symbol]
                for symbol in keysyms
                if symbol in keyboard._overlay
            )
            available = sum(code not in protected for code in keyboard._spare_keycodes)
            if len(missing) > available:
                return False
        previous = dict(keyboard._overlay)
        result = original(keyboard, keysyms)
        if result and previous != keyboard._overlay:
            mapping = _read_keymap()
            try:
                subprocess.run(
                    [_XKBCOMP, "-", os.environ["DISPLAY"]],
                    input=mapping,
                    check=True,
                    capture_output=True,
                    timeout=2,
                )
            except (OSError, subprocess.SubprocessError, KeyError):
                raise RuntimeError("X11 keyboard map refresh failed") from None
            # Preserve the SDK's application settle after the replacement too.
            keyboard._settle_until = time.monotonic() + keyboard._BIND_SETTLE_S
        return result

    _XTestKeyboard._find_spare_keycodes = find_named_spares
    _XTestKeyboard.text_room = text_room
    _XTestKeyboard.prebind = prebind_with_refresh
    _installed = True
