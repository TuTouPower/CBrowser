"""Keep native Selkies text overlays coherent with Chromium's XKB cache.

An active Chromium can retain its old map after core symbol changes. Reloading
that map broadcasts a keyboard replacement, provided every spare has an XKB
name: unnamed keys coalesce during serialization. Input remains native XTest.
"""

import inspect
import os
import re
import subprocess
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


def install_x11_keymap_refresh() -> None:
    """Install the version-bound adapter before the native input handler starts."""
    global _installed
    if _installed:
        return
    if version("selkies") != "2.1.0" or not Path(_XKBCOMP).is_file():
        raise RuntimeError("Unsupported X11 input runtime")

    from selkies.input_handler import _XTestKeyboard

    original = _XTestKeyboard.prebind
    original_room = _XTestKeyboard.text_room
    original_spares = _XTestKeyboard._find_spare_keycodes
    for method, parameters in (
        (original, ["self", "keysyms"]),
        (original_room, ["self"]),
        (original_spares, ["self"]),
    ):
        if list(inspect.signature(method).parameters) != parameters:
            raise RuntimeError("Unsupported Selkies text binding ABI")

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
