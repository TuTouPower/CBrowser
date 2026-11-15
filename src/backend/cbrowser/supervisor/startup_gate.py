"""CBrowser runtime startup gate.

Waits boundedly for sibling ready.json matching instance_id and role,
validates marker payload, then os.execv the target application entrypoint.
Standard library only; compatible with direct execution in existing Runtime images.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="CBrowser runtime startup gate",
        prog="startup_gate",
    )
    parser.add_argument(
        "--instance-id",
        required=True,
        help="Expected runtime instance ID",
    )
    parser.add_argument(
        "--role",
        required=True,
        choices=["browser", "stream"],
        help="Runtime container role",
    )
    parser.add_argument(
        "--gate-dir",
        default="/run/cbrowser_policy",
        help="Directory containing ready.json marker",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Bounded wait timeout in seconds (default 60.0)",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.1,
        help="Polling interval in seconds (default 0.1)",
    )

    if "--" in argv:
        split_idx = argv.index("--")
        gate_args = argv[:split_idx]
        app_cmd = argv[split_idx + 1 :]
    else:
        gate_args = argv
        app_cmd = []

    parsed = parser.parse_args(gate_args)
    if not app_cmd:
        parser.error("Missing application command after '--'")
    return parsed, app_cmd


def wait_for_marker(
    gate_dir: Path,
    expected_instance_id: str,
    expected_role: str,
    timeout: float = 60.0,
    poll_interval: float = 0.1,
) -> bool:
    marker_path = gate_dir / "ready.json"
    start_time = time.monotonic()
    deadline = start_time + timeout

    while time.monotonic() < deadline:
        if marker_path.is_file():
            try:
                raw_bytes = marker_path.read_bytes()
                if not raw_bytes:
                    time.sleep(poll_interval)
                    continue
                data = json.loads(raw_bytes.decode("utf-8"))
                if not isinstance(data, dict):
                    sys.stderr.write(
                        f"StartupGate: malformed ready.json at {marker_path}\n"
                    )
                    return False
                marker_instance = str(data.get("instance_id") or "")
                marker_role = str(data.get("role") or "")
                marker_status = str(data.get("status") or "")

                if marker_status != "ready":
                    sys.stderr.write(
                        f"StartupGate: ready.json status {marker_status!r} != 'ready'\n"
                    )
                    return False

                if (
                    marker_instance != expected_instance_id
                    or marker_role != expected_role
                ):
                    sys.stderr.write(
                        f"StartupGate: mismatched marker instance={marker_instance!r} "
                        f"role={marker_role!r} "
                        f"(expected={expected_instance_id!r}/{expected_role!r})\n"
                    )
                    return False

                return True
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                sys.stderr.write(
                    f"StartupGate: JSON decode error reading marker: {exc}\n"
                )
                return False
            except OSError as exc:
                sys.stderr.write(f"StartupGate: I/O error reading marker: {exc}\n")
                return False

        time.sleep(poll_interval)

    sys.stderr.write(
        f"StartupGate: timeout ({timeout}s) waiting for ready.json in {gate_dir}\n"
    )
    return False


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    args, app_cmd = parse_args(argv)
    gate_dir = Path(args.gate_dir)

    success = wait_for_marker(
        gate_dir=gate_dir,
        expected_instance_id=args.instance_id,
        expected_role=args.role,
        timeout=args.timeout,
        poll_interval=args.poll_interval,
    )

    if not success:
        sys.exit(1)

    os.execv(app_cmd[0], app_cmd)


if __name__ == "__main__":
    main()
