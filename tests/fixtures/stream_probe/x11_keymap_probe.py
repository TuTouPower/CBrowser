"""Exercise native spare reuse against a real X server and XKB map reloads."""

import json

from cbrowser.stream_agent.x11_keymap import install_x11_keymap_refresh
from selkies.input_handler import _XTestKeyboard, overlay_bind_keysym
from selkies.Xlib import display

install_x11_keymap_refresh()
installed = _XTestKeyboard.prebind
install_x11_keymap_refresh()
assert _XTestKeyboard.prebind is installed
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
        json.dumps({"rounds": rounds, "idempotent": True, "held_slots_unchanged": True})
    )
finally:
    connection.close()
