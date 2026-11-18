"""Shared named-volume topology constants (t080 / ADR 029, t082 / ADR 039).

Kept pure-stdlib in ``cbrowser.shared`` so both deploy-time volume scripts
(running inside the API image or host Python) and the Supervisor's
``MountPlanner`` consume one authoritative layout definition without
pulling Docker SDK dependencies into deploy helpers.
"""

from __future__ import annotations

VOLUME_KINDS = ("db", "data", "fonts", "runtime")

# Default non-root runtime UID/GID used across API, Browser, Stream, and volumes.
RUNTIME_UID = 1000
RUNTIME_GID = 1000

# Subpath prefixes inside the runtime volume (ADR 029 + ADR 039).
RUNTIME_GATES_PREFIX = "gates"
RUNTIME_SOCKETS_PREFIX = "sockets"
RUNTIME_POLICY_AGENTS_PREFIX = "policy-agents"
RUNTIME_SECRETS_PREFIX = ".secrets"

DATA_VOLUME_LAYOUT = (
    "profiles",
    "runtime",
    "runtime-events",
    "artifacts",
    "spool",
    "control",
    "control/gates",
    "control/policy-agents",
    "engine-cache/geoip",
    "network",
)

RUNTIME_VOLUME_LAYOUT = (
    RUNTIME_GATES_PREFIX,
    RUNTIME_SOCKETS_PREFIX,
    RUNTIME_POLICY_AGENTS_PREFIX,
    RUNTIME_SECRETS_PREFIX,
)

FONTS_VOLUME_LAYOUT = ("macos", "windows")
