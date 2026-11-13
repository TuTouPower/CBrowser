"""Shared neutral modules used by more than one service image.

Modules here must not import any cbrowser service package (api, auth,
services, gateway, supervisor, adapters, runtime_agent, stream_agent,
agent_executor, font_sets): every service image ships this package, so
a service dependency would drag that service into every image. The
only cbrowser import allowed is the ``secret_files`` leaf utility,
which every shared-shipping image also ships. This discipline is
guarded by tests/unit/test_t062_boundaries.py.
"""

from __future__ import annotations
