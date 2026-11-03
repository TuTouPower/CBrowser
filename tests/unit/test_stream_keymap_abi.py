"""Selkies private-ABI verification for the X11 keymap adapter (t022 A47)."""

from __future__ import annotations

import pytest
from cbrowser.stream_agent.x11_keymap import _verify_selkies_keyboard_abi


def _complete_keyboard():
    class Keyboard:
        _BIND_SETTLE_S = 0.025

        def __init__(self, xdisplay):
            self._spare_keycodes = None
            self._spare_set = frozenset()
            self._text_codes = 0
            self._overlay = {}
            self._pressed_kc = {}
            self._settle_until = 0.0

        def prebind(self, keysyms):
            return True

        def text_room(self):
            return 0

        def _find_spare_keycodes(self):
            return []

        def _layout_keycode(self, keysym):
            return 0

    return Keyboard


def test_complete_abi_surface_passes() -> None:
    _verify_selkies_keyboard_abi(_complete_keyboard())


def test_missing_method_is_unsupported_abi() -> None:
    keyboard = _complete_keyboard()
    del keyboard._layout_keycode
    with pytest.raises(RuntimeError, match="Unsupported Selkies text binding ABI"):
        _verify_selkies_keyboard_abi(keyboard)


def test_wrong_signature_is_unsupported_abi() -> None:
    keyboard = _complete_keyboard()
    keyboard.prebind = lambda self: True  # noqa: ARG005 - deliberately wrong ABI
    with pytest.raises(RuntimeError, match="Unsupported Selkies text binding ABI"):
        _verify_selkies_keyboard_abi(keyboard)


def test_missing_instance_attribute_is_unsupported_abi() -> None:
    class Keyboard(_complete_keyboard()):
        def __init__(self, xdisplay):
            self._spare_keycodes = None
            self._spare_set = frozenset()
            self._text_codes = 0
            self._overlay = {}
            self._pressed_kc = {}
            # _settle_until deliberately absent

    with pytest.raises(RuntimeError, match="_settle_until"):
        _verify_selkies_keyboard_abi(Keyboard)


def test_missing_settle_constant_is_unsupported_abi() -> None:
    keyboard = _complete_keyboard()
    keyboard._BIND_SETTLE_S = 0
    with pytest.raises(RuntimeError, match="_BIND_SETTLE_S"):
        _verify_selkies_keyboard_abi(keyboard)


def test_attributes_in_comments_do_not_satisfy_the_abi() -> None:
    """f009: the attribute check is AST-based — names that appear only in
    comments or strings inside __init__ are not assignments."""
    keyboard = _complete_keyboard()

    def commented_init(self, xdisplay):
        # self._spare_keycodes self._spare_set self._text_codes
        # self._overlay self._pressed_kc self._settle_until
        self._other = None

    keyboard.__init__ = commented_init
    with pytest.raises(RuntimeError, match="Unsupported Selkies text binding ABI"):
        _verify_selkies_keyboard_abi(keyboard)


def test_unintrospectable_signature_is_unsupported_not_a_crash() -> None:
    """f009: a callable whose signature cannot be introspected reports
    unsupported ABI instead of leaking TypeError/ValueError."""
    keyboard = _complete_keyboard()
    keyboard.prebind = print  # builtin: signature exists but mismatches
    with pytest.raises(RuntimeError, match="Unsupported Selkies text binding ABI"):
        _verify_selkies_keyboard_abi(keyboard)
