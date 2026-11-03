"""Whitelist validation for user-provided Chrome launch arguments."""

from __future__ import annotations

import re

ALLOWED_BOOLEAN_FLAGS = frozenset(
    {
        "--disable-background-networking",
        "--disable-backgrounding-occluded-windows",
        "--disable-client-side-phishing-detection",
        "--disable-component-extensions-with-background-pages",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-hang-monitor",
        "--disable-ipc-flooding-protection",
        "--disable-prompt-on-repost",
        "--disable-renderer-backgrounding",
        "--disable-sync",
        "--disable-translate",
        "--metrics-recording-only",
        "--mute-audio",
        "--no-default-browser-check",
        "--no-first-run",
        "--password-store=basic",
        "--use-mock-keychain",
    }
)

_EXACT_FLAGS = frozenset(
    {
        "--disable-blink-features=AutomationControlled",
    }
)

_LOCALE = r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*"
_VALUE_PATTERNS = {
    "--lang": re.compile(rf"^{_LOCALE}$"),
    "--accept-lang": re.compile(rf"^{_LOCALE}(?:,{_LOCALE})*$"),
}
_CONTROL_CHARS = re.compile(r"[\r\n\x00-\x1f]")


class InvalidLaunchArgument(ValueError):
    """Raised when a user launch argument is outside the supported whitelist."""


def validate_launch_arg(arg: str) -> str:
    if not isinstance(arg, str):
        raise InvalidLaunchArgument("Launch arguments must be strings")
    clean = arg.strip()
    if not clean or _CONTROL_CHARS.search(clean):
        raise InvalidLaunchArgument("Launch argument contains invalid characters")
    if clean in _EXACT_FLAGS or clean in ALLOWED_BOOLEAN_FLAGS:
        return clean
    name, separator, value = clean.partition("=")
    if separator and name in _VALUE_PATTERNS:
        if _VALUE_PATTERNS[name].fullmatch(value):
            return clean
    raise InvalidLaunchArgument(f"Launch argument is not allowed: {name}")


def validate_launch_args(args: list[str] | None) -> list[str]:
    if not args:
        return []
    return [validate_launch_arg(arg) for arg in args]


def filter_launch_args(args: list[str] | None) -> list[str]:
    """Drop arguments no longer in the whitelist (legacy DB rows/snapshots)."""
    if not args:
        return []
    accepted: list[str] = []
    for arg in args:
        try:
            accepted.append(validate_launch_arg(arg))
        except InvalidLaunchArgument:
            continue
    return accepted
