"""p057: container event trigger policy for the reconciliation accelerator.

The Docker event watcher used to wake the scan on every event of every
prefixed container, including healthcheck ``exec_*`` actions and the
lifecycle of Supervisor-owned transient helpers. A scan installs a policy
helper, so helper lifecycle events woke the next scan: a self-exciting
loop. Only business topology events may trigger a scan.
"""

from __future__ import annotations

import threading

from cbrowser.supervisor.runner import (
    _pump_container_events,
    container_event_triggers_scan,
)

PREFIX = "cbrowser-t005"


def _event(action: str, role: str = "browser", prefix: str = PREFIX) -> dict:
    return {
        "Type": "container",
        "Action": action,
        "Actor": {
            "Attributes": {
                "com.cbrowser.prefix": prefix,
                "com.cbrowser.role": role,
            }
        },
    }


def test_business_topology_actions_trigger_scan():
    for action in (
        "create",
        "start",
        "restart",
        "die",
        "destroy",
        "kill",
        "stop",
        "oom",
        "pause",
        "unpause",
        "rename",
    ):
        assert container_event_triggers_scan(_event(action), PREFIX), action


def test_business_roles_trigger_scan():
    for role in ("browser", "stream", "gateway"):
        assert container_event_triggers_scan(_event("die", role), PREFIX), role


def test_healthcheck_exec_events_do_not_trigger_scan():
    for action in ("exec_create", "exec_start", "exec_die", "exec_detach"):
        for role in ("api", "gateway", "supervisor", "caddy"):
            assert not container_event_triggers_scan(
                _event(action, role), PREFIX
            ), (action, role)


def test_supervisor_transient_helpers_do_not_trigger_scan():
    for role in ("network-policy", "x11-permissions", "cache-init"):
        for action in ("create", "start", "die", "destroy"):
            assert not container_event_triggers_scan(
                _event(action, role), PREFIX
            ), (action, role)


def test_infrastructure_roles_do_not_trigger_scan():
    for role in ("api", "caddy", "supervisor"):
        assert not container_event_triggers_scan(_event("die", role), PREFIX)


def test_foreign_prefix_does_not_trigger_scan():
    assert not container_event_triggers_scan(
        _event("die", "browser", prefix="other"), PREFIX
    )


def test_non_lifecycle_actions_do_not_trigger_scan():
    for action in ("attach", "detach", "copy", "top", "update", "export"):
        assert not container_event_triggers_scan(_event(action), PREFIX), action


def test_malformed_events_do_not_trigger_scan():
    assert not container_event_triggers_scan({}, PREFIX)
    assert not container_event_triggers_scan({"Actor": None}, PREFIX)
    assert not container_event_triggers_scan("not-a-dict", PREFIX)
    assert not container_event_triggers_scan(None, PREFIX)
    assert not container_event_triggers_scan(
        {"Type": "network", "Action": "create",
         "Actor": {"Attributes": {
             "com.cbrowser.prefix": PREFIX, "com.cbrowser.role": "browser"}}},
        PREFIX,
    )


def test_pump_wakes_only_for_business_topology_events_close():
    hits: list[str] = []
    stop = threading.Event()
    events = iter(
        [
            _event("exec_die", "gateway"),
            _event("create", "network-policy"),
            _event("die", "browser"),
            _event("destroy", "network-policy"),
            _event("start", "stream"),
        ]
    )
    _pump_container_events(events, PREFIX, lambda: hits.append("wake"), stop)
    assert hits == ["wake", "wake"]


def test_pump_stops_after_match_when_stop_set():
    hits: list[str] = []
    stop = threading.Event()

    def _on_match() -> None:
        hits.append("wake")
        stop.set()

    events = iter([_event("die", "browser"), _event("die", "stream")])
    _pump_container_events(events, PREFIX, _on_match, stop)
    assert hits == ["wake"]
