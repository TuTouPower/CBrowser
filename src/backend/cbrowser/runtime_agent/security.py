"""Security and argument sanitization for Browser Runtime."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("cbrowser.runtime_agent.security")

# Flags that are strictly reserved for the runtime infrastructure
RESERVED_PREFIXES = (
    "--remote-debugging-port",
    "--remote-debugging-address",
    "--remote-debugging-pipe",
    "--remote-debugging-targets",
    "--remote-allow-origins",
    "--user-data-dir",
    "--display",
    "--force-device-scale-factor",
    "--window-size",
    "--window-position",
    "--headless",
)

# Unsafe execution flags that must never be permitted from user profiles
UNSAFE_FLAGS = (
    "--renderer-cmd-prefix",
    "--gpu-launcher",
    "--utility-cmd-prefix",
    "--ppapi-plugin-launcher",
    "--extra-plugin-dir",
    "--allow-file-access-from-files",
    "--disable-web-security",
    "--no-sandbox",
)

DISALLOWED_PATTERN = re.compile(r"[\r\n\x00-\x1f]")
RUNTIME_ID_PATTERN = re.compile(r"[a-zA-Z0-9_\-.:]{1,128}")


def validate_runtime_id(value: str) -> str:
    """Require a safe single path component without echoing rejected input."""
    if (
        not isinstance(value, str)
        or not RUNTIME_ID_PATTERN.fullmatch(value)
        or value in (".", "..")
    ):
        raise ValueError("Invalid runtime identity")
    return value


def is_flag_safe(arg: str) -> bool:
    """Validate whether an individual launch argument is safe."""
    if not isinstance(arg, str):
        return False
    if DISALLOWED_PATTERN.search(arg):
        logger.warning("Rejecting argument with control characters")
        return False
    clean = arg.strip()
    if not clean:
        return False

    prefix = clean.split("=", 1)[0].lower()

    if any(prefix == res or prefix.startswith(res + "=") for res in RESERVED_PREFIXES):
        logger.warning("Dropping reserved infrastructure flag override: %s", prefix)
        return False

    if prefix in UNSAFE_FLAGS:
        logger.warning("Rejecting unsafe launch flag")
        return False

    if prefix == "--disable-features":
        features = clean.partition("=")[2].split(",")
        if any(
            feature.strip().split("<", 1)[0].split(":", 1)[0].casefold()
            == "isolateorigins"
            for feature in features
        ):
            logger.warning("Rejecting unsafe feature override")
            return False

    return True


def sanitize_launch_args(args: list[str] | None) -> list[str]:
    """Filter and sanitize user-provided launch arguments."""
    if not args:
        return []
    safe_args: list[str] = []
    for a in args:
        if is_flag_safe(a):
            safe_args.append(a.strip())
    return safe_args
