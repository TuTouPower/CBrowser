"""Production steady-state probe (t083).

Samples one window of a running stack and reports the counters the
steady-state acceptance is stated in:

- Docker execs created by the stack itself.  ``exec_create`` is the
  one event that represents an execution; ``exec_start``/``exec_die``
  are stage events of the same execution and are reported separately,
  never added into the exec count.
- Policy churn: create/destroy of one-shot ``network-policy`` helper
  containers and of ``network-policy-agent`` containers (both must be
  zero in steady state; Agents are created at Profile start only).
- Container lifecycle events and restart counts per container, so an
  instance restart inside the window is visible, not averaged away.
- Optional rchar deltas for the API/Supervisor containers, read via
  ``docker exec cat /proc/1/io`` at the window edges.  Those reads are
  the probe's own execs: they are tagged as measurement overhead and
  excluded from the stack exec count.

The probe itself runs on the host against the Docker CLI; it never
counts its own event stream connection as stack activity.  Output is
one JSON object; the aggregation core (``aggregate_events``) is pure
so the counting rules are unit-testable without Docker.

Usage:
    steady_state_probe.py --prefix cbrowser --duration 600 \
        [--rchar] [--out evidence.json]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from typing import Any, Iterable

POLICY_ROLES = {"network-policy", "network-policy-agent"}


def _labels(event: dict[str, Any]) -> dict[str, str]:
    actor = event.get("Actor") or {}
    attrs = actor.get("Attributes") or {}
    return {str(k): str(v) for k, v in attrs.items()}


def aggregate_events(
    events: Iterable[dict[str, Any]],
    *,
    prefix: str,
    measurement_exec_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Fold raw Docker events into steady-state counters.

    Only containers of this stack (``com.cbrowser.prefix`` label or
    the ``<prefix>-`` name convention) are counted.  Exec ids the
    caller marks as its own measurement execs are reported under
    ``measurement_execs`` and excluded from ``stack_execs``.
    """
    measurement_exec_ids = measurement_exec_ids or set()
    stack_execs = 0
    measurement_execs = 0
    exec_stage_events = 0
    policy_churn = 0
    policy_agent_churn = 0
    lifecycle: dict[str, dict[str, int]] = {}
    restarts_observed: dict[str, int] = {}

    for event in events:
        if event.get("Type") != "container":
            continue
        labels = _labels(event)
        name = labels.get("name", "")
        if labels.get("com.cbrowser.prefix") not in (None, prefix):
            continue
        if (
            labels.get("com.cbrowser.prefix") is None
            and not name.startswith(f"{prefix}-")
            and labels.get("com.cbrowser.managed-by") != "supervisor"
        ):
            continue
        action = str(event.get("Action", ""))
        container_id = str((event.get("Actor") or {}).get("ID", ""))
        role = labels.get("com.cbrowser.role", "")

        if action.startswith("exec_create"):
            # Docker reports the exec id after the colon in the Action
            # (``exec_create: <exec-id>``); the part before the colon is
            # the literal action name and never matches a real exec id.
            exec_id = (
                action.split(":", 1)[1].strip()
                if ":" in action
                else ""
            )
            # The caller marks its own measurement execs by container +
            # command instead, so membership is checked on both.
            marker = f"{container_id}:{action}"
            if (
                exec_id in measurement_exec_ids
                or marker in measurement_exec_ids
                or labels.get("com.cbrowser.measurement") == "steady-state-probe"
            ):
                measurement_execs += 1
            else:
                stack_execs += 1
            continue
        if action.startswith("exec_start") or action.startswith(
            "exec_die"
        ):
            exec_stage_events += 1
            continue
        if action in ("create", "destroy", "die", "start", "restart"):
            per = lifecycle.setdefault(
                container_id, {"name": name, "role": role}
            )
            per[action] = per.get(action, 0) + 1  # type: ignore[assignment]
            if role == "network-policy" and action in ("create", "destroy"):
                policy_churn += 1
            if role == "network-policy-agent" and action in (
                "create",
                "destroy",
            ):
                policy_agent_churn += 1
            if action == "restart":
                restarts_observed[container_id] = (
                    restarts_observed.get(container_id, 0) + 1
                )

    return {
        "stack_execs": stack_execs,
        "measurement_execs": measurement_execs,
        "exec_stage_events": exec_stage_events,
        "policy_helper_churn_events": policy_churn,
        "policy_agent_churn_events": policy_agent_churn,
        "lifecycle_by_container": lifecycle,
        "restarts_observed": restarts_observed,
    }


class DockerCommandError(RuntimeError):
    """A `docker` CLI call failed; its output must never be read as an
    all-zero steady-state window."""


def _docker_json_lines(args: list[str]) -> list[dict[str, Any]]:
    out = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise DockerCommandError(
            f"docker {' '.join(args)} failed (exit {out.returncode}): "
            f"{out.stderr.strip()[:500]}"
        )
    rows: list[dict[str, Any]] = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _inspect_stack(prefix: str) -> dict[str, dict[str, Any]]:
    rows = _docker_json_lines(
        [
            "inspect",
            *[
                row["Id"]
                for row in _docker_json_lines(
                    [
                        "ps",
                        "-aq",
                        "--filter",
                        f"label=com.cbrowser.prefix={prefix}",
                        "--format",
                        "{{json .}}",
                    ]
                )
            ],
        ]
    ) if prefix else []
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        result[str(row.get("Id", ""))] = {
            "name": str(row.get("Name", "")).lstrip("/"),
            "role": (row.get("Config", {}).get("Labels") or {}).get(
                "com.cbrowser.role", ""
            ),
            "restart_count": int(row.get("RestartCount", 0)),
            "started_at": row.get("State", {}).get("StartedAt"),
        }
    return result


def _read_rchar(container: str) -> int | None:
    out = subprocess.run(
        ["docker", "exec", container, "cat", "/proc/1/io"],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in out.stdout.splitlines():
        if line.startswith("rchar:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def run_probe(
    *, prefix: str, duration: float, with_rchar: bool
) -> dict[str, Any]:
    before = _inspect_stack(prefix)
    rchar_before: dict[str, int | None] = {}
    if with_rchar:
        for info in before.values():
            if info["role"] in ("api", "supervisor") or info["name"].endswith(
                ("-api", "-supervisor")
            ):
                rchar_before[info["name"]] = _read_rchar(info["name"])
    # Unix epoch seconds: Docker parses a naive "%Y-%m-%dT%H:%M:%S"
    # timestamp in the *client's* local timezone, so a UTC string would
    # shift the sampled window by the host offset (8h on a UTC+8 Mac).
    # Epoch seconds are unambiguous everywhere.
    since_epoch = int(time.time())
    time.sleep(duration)
    until_epoch = int(time.time())
    events = _docker_json_lines(
        [
            "events",
            "--since",
            str(since_epoch),
            "--until",
            str(until_epoch),
            "--filter",
            "type=container",
            "--format",
            "{{json .}}",
        ]
    )
    after = _inspect_stack(prefix)
    rchar_after: dict[str, int | None] = {}
    if with_rchar:
        for info in after.values():
            if info["name"] in rchar_before:
                rchar_after[info["name"]] = _read_rchar(info["name"])
    counters = aggregate_events(events, prefix=prefix)
    restart_deltas = {}
    for cid, info in after.items():
        prior = before.get(cid)
        if prior is not None and info["restart_count"] != prior["restart_count"]:
            restart_deltas[info["name"]] = (
                info["restart_count"] - prior["restart_count"]
            )
    rchar_deltas = {}
    for name, start_value in rchar_before.items():
        end_value = rchar_after.get(name)
        if start_value is not None and end_value is not None:
            rchar_deltas[name] = end_value - start_value
    return {
        "prefix": prefix,
        "duration_sec": duration,
        "window_epoch": {"since": since_epoch, "until": until_epoch},
        "counters": counters,
        "restart_count_deltas": restart_deltas,
        "rchar_deltas": rchar_deltas,
        "containers_before": sorted(
            info["name"] for info in before.values()
        ),
        "containers_after": sorted(
            info["name"] for info in after.values()
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default="cbrowser")
    parser.add_argument("--duration", type=float, default=600.0)
    parser.add_argument("--rchar", action="store_true")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    try:
        result = run_probe(
            prefix=args.prefix, duration=args.duration, with_rchar=args.rchar
        )
    except DockerCommandError as exc:
        # A failed collection is not a clean window: fail loudly and
        # never emit an all-zero report for a window we did not sample.
        print(f"steady-state probe failed: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
