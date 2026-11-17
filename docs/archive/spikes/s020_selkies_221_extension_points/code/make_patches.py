#!/usr/bin/env python3
"""Spike prototype: generate the controlled-build patches for selkies 2.2.1.

Applies exact, single-occurrence text replacements to the pinned upstream
wheel's ``selkies/__main__.py`` and ``selkies/input_handler.py`` and emits
unified diffs.  Fail-closed: any anchor that does not occur exactly once
aborts the generation.
"""

from __future__ import annotations

import difflib
import hashlib
import sys
import zipfile
from pathlib import Path

WHEEL_SHA256 = "18503b5c1491a04194f0a45fa10c547ffe5b4a24f33496ce5d56e97370a6a3cd"

MAIN_REPLACEMENTS: list[tuple[str, str]] = [
    (
        "import os\nimport signal\nimport asyncio\nimport logging\n",
        "import os\nimport signal\nimport asyncio\nimport importlib\nimport logging\n",
    ),
    (
        'async def run() -> None:\n    """Build the stream server, register its services, and run until canceled.\n',
        '''def _webrtc_service(server):
    """Build the WebRTC service registered under the ``webrtc`` name.

    An embedding application may name an alternate service factory via
    the ``SELKIES_WEBRTC_SERVICE_FACTORY`` environment variable in
    ``module:attribute`` form; the attribute must be a callable taking
    the stream server and returning the service instance.  Without the
    override the stock :class:`WebRTCService` is used.
    """
    factory_ref = os.environ.get("SELKIES_WEBRTC_SERVICE_FACTORY")
    if not factory_ref:
        return WebRTCService(server)
    module_name, separator, attribute = factory_ref.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError(
            "SELKIES_WEBRTC_SERVICE_FACTORY must be in module:attribute form"
        )
    factory = getattr(importlib.import_module(module_name), attribute)
    return factory(server)


async def run() -> None:
    """Build the stream server, register its services, and run until canceled.
''',
    ),
    (
        '    server.register_service("webrtc", WebRTCService(server))\n',
        '    server.register_service("webrtc", _webrtc_service(server))\n',
    ),
]

_KEYBOARD_HELPERS = '''
# --- Controlled-build additions: XKB keymap coherence -------------------
# An active Chromium can retain its old map after core symbol changes.
# Reloading that map broadcasts a keyboard replacement, provided every
# spare has an XKB name: unnamed keys coalesce during serialization.

_XKBCOMP_PATH = "/usr/bin/xkbcomp"


def _read_xkb_keymap() -> bytes:
    import subprocess

    try:
        return subprocess.run(
            [_XKBCOMP_PATH, "-xkb", os.environ["DISPLAY"], "-"],
            check=True,
            capture_output=True,
            timeout=2,
        ).stdout
    except (OSError, subprocess.SubprocessError, KeyError):
        # Keyboard maps contain private text symbols; never attach output.
        raise RuntimeError("X11 keyboard map query failed") from None


def _xkb_named_keycodes() -> set:
    """Keycodes carrying a non-empty XKB name in the live server map."""
    return {
        int(match.group(1))
        for match in re.finditer(
            rb"^\\s*<[^>]+>\\s*=\\s*(\\d+);", _read_xkb_keymap(), re.MULTILINE
        )
    }


def _reload_xkb_keymap() -> None:
    import subprocess

    mapping = _read_xkb_keymap()
    try:
        subprocess.run(
            [_XKBCOMP_PATH, "-", os.environ["DISPLAY"]],
            input=mapping,
            check=True,
            capture_output=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError, KeyError):
        raise RuntimeError("X11 keyboard map refresh failed") from None


'''

INPUT_HANDLER_REPLACEMENTS: list[tuple[str, str]] = [
    (
        "class _XTestKeyboard:\n",
        _KEYBOARD_HELPERS + "class _XTestKeyboard:\n",
    ),
    (
        """        self._spare_set = frozenset(spares)
        text = [kc for kc in self._TEXT_SPARES if kc in self._spare_set]
        keysym, evdev_kc = self._EVDEV_LEFT
        self._text_codes = 0 if self._d.keysym_to_keycode(keysym) == evdev_kc else len(text)
        return text + [kc for kc in spares if kc not in text]
""",
        """        self._spare_set = frozenset(spares)
        text = [kc for kc in self._TEXT_SPARES if kc in self._spare_set]
        keysym, evdev_kc = self._EVDEV_LEFT
        self._text_codes = 0 if self._d.keysym_to_keycode(keysym) == evdev_kc else len(text)
        pool = text + [kc for kc in spares if kc not in text]
        # Controlled build: unnamed keys coalesce when the map is
        # serialized for a reload, so only XKB-named spares may serve as
        # overlay keycodes.  Fail loudly when the live map has no names.
        named = _xkb_named_keycodes()
        if not named:
            raise RuntimeError("X11 keyboard names unavailable")
        preferred = set(pool[: self._text_codes])
        pool = [kc for kc in pool if kc in named]
        self._spare_set = frozenset(pool)
        self._text_codes = sum(kc in preferred for kc in pool)
        return pool
""",
    ),
    (
        """        held = set(self._pressed_kc.values())
        return sum(kc not in held for kc in self._spare_keycodes[:self._text_codes])
""",
        """        held = set(self._pressed_kc.values())
        room = sum(kc not in held for kc in self._spare_keycodes[:self._text_codes])
        if room:
            return room
        # Controlled build: on evdev keycodes _text_codes is 0 (binds are
        # not kept to the text prefix), yet prebind draws on the whole
        # pool; report free pool slots instead of a false zero.
        return sum(kc not in held for kc in self._spare_keycodes)
""",
    ),
    (
        """        if self._spare_keycodes is None:
            self._spare_keycodes = self._find_spare_keycodes()
        if len(missing) > len(self._spare_keycodes):
            return False
        assigns = sorted((self._alloc_overlay_keycode(ks, keep=batch), ks) for ks in missing)
""",
        """        if self._spare_keycodes is None:
            self._spare_keycodes = self._find_spare_keycodes()
        # Controlled build: keycodes already pressed or holding a batch
        # keysym's binding are not capacity; never promise binds that
        # would recycle them mid-batch.
        protected = set(self._pressed_kc.values())
        protected.update(self._overlay[ks] for ks in batch if ks in self._overlay)
        if len(missing) > sum(kc not in protected for kc in self._spare_keycodes):
            return False
        previous_overlay = dict(self._overlay)
        assigns = sorted((self._alloc_overlay_keycode(ks, keep=batch), ks) for ks in missing)
""",
    ),
    (
        """        d.sync()
        # One settle deadline for the whole batch, since one sync covers it.
        self._settle_until = time.monotonic() + self._BIND_SETTLE_S
        return True
""",
        """        d.sync()
        # One settle deadline for the whole batch, since one sync covers it.
        self._settle_until = time.monotonic() + self._BIND_SETTLE_S
        if previous_overlay != self._overlay:
            # Controlled build: broadcast the replacement map so an active
            # Chromium refetches it instead of reading a rebound keycode by
            # its previous symbol; re-arm the same settle span afterwards.
            _reload_xkb_keymap()
            self._settle_until = time.monotonic() + self._BIND_SETTLE_S
        return True
""",
    ),
]

FILES = {
    "selkies/__main__.py": MAIN_REPLACEMENTS,
    "selkies/input_handler.py": INPUT_HANDLER_REPLACEMENTS,
}


def apply_replacements(name: str, text: str, replacements: list[tuple[str, str]]) -> str:
    for old, new in replacements:
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"{name}: anchor occurs {count} times (expected 1): {old[:60]!r}")
        text = text.replace(old, new)
    return text


def main() -> int:
    wheel_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(wheel_path.read_bytes()).hexdigest()
    assert digest == WHEEL_SHA256, f"wheel hash mismatch: {digest}"
    with zipfile.ZipFile(wheel_path) as z:
        for name, replacements in FILES.items():
            original = z.read(name).decode("utf-8")
            patched = apply_replacements(name, original, replacements)
            diff = difflib.unified_diff(
                original.splitlines(keepends=True),
                patched.splitlines(keepends=True),
                fromfile=f"a/{name}",
                tofile=f"b/{name}",
            )
            patch_name = name.replace("/", "_") + ".patch"
            (out_dir / patch_name).write_text("".join(diff), encoding="utf-8")
            (out_dir / (name.replace("/", "_") + ".patched")).write_text(patched, encoding="utf-8")
            print(f"{name}: patch written ({patch_name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
