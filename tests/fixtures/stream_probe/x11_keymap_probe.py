"""Exercise native spare reuse against a real X server and XKB map reloads.

t063: the keymap coherence behavior ships inside the controlled Selkies
build installed in the stream image; there is no runtime wrapper to
install.  This probe verifies the installed package really is the
controlled build and that its native bindings survive repeated reuse.
"""

import importlib.metadata
import importlib.util
import json
import re
from pathlib import Path

from selkies.input_handler import _XTestKeyboard, overlay_bind_keysym
from selkies.Xlib import display

version = importlib.metadata.version("selkies")
assert version.startswith("2.2.1+cbrowser."), (
    f"stream image must carry the controlled Selkies build, got {version}"
)
stamp_path = (
    Path(importlib.util.find_spec("selkies").origin).parent / "cbrowser_build.json"
)
stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
assert stamp["controlled_version"] == version, (
    f"build stamp {stamp['controlled_version']} != installed {version}"
)
assert stamp["upstream"]["wheel_sha256"] == (
    "18503b5c1491a04194f0a45fa10c547ffe5b4a24f33496ce5d56e97370a6a3cd"
), "build stamp upstream identity is not the pinned 2.2.1 wheel"
assert len(stamp["patches"]) == 2 and all(
    re.fullmatch(r"[0-9a-f]{64}", p["sha256"]) for p in stamp["patches"]
), "build stamp patch series is incomplete"
connection = display.Display(":99")
keyboard = _XTestKeyboard(connection)
capacity = keyboard.text_room()
assert capacity > 0
assert keyboard.prebind([0x1004E2D, 0x1006587, 0x1008F93, 0x1005165])
rounds = []
try:
    for index in range(5):
        symbols = [0x1004E00 + index * capacity + offset for offset in range(capacity)]
        assert keyboard.prebind(symbols)
        lo = connection.display.info.min_keycode
        hi = connection.display.info.max_keycode
        actual = connection.get_keyboard_mapping(lo, hi - lo + 1)
        assert all(
            actual[code - lo][0] == overlay_bind_keysym(symbol)
            for symbol, code in keyboard._overlay.items()
        ), "XKB reload changed a live native binding"
        assert all(symbol in keyboard._overlay for symbol in symbols)
        rounds.append({"capacity": capacity, "bindings": len(keyboard._overlay)})
    # Physically held spare keys must never be rebound by a composition batch.
    held_symbols = list(keyboard._overlay)
    try:
        for symbol in held_symbols:
            keyboard.press(symbol)
        connection.sync()
        before = connection.get_keyboard_mapping(lo, hi - lo + 1)
        assert not keyboard.prebind([0x1006000]), (
            "Prebind reused a physically held slot"
        )
        assert connection.get_keyboard_mapping(lo, hi - lo + 1) == before
    finally:
        for symbol in held_symbols:
            keyboard.release(symbol)
        connection.sync()
    print(
        json.dumps(
            {
                "rounds": rounds,
                "controlled_build": True,
                "controlled_version": version,
                "stamp_verified": True,
                "held_slots_unchanged": True,
            }
        )
    )
finally:
    connection.close()
