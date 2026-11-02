#!/bin/bash
set -euo pipefail

PROFILE_ID=""
RUNTIME_INSTANCE_ID=""
CONFIG_SNAPSHOT=""
RUN_DIR="/run/cbrowser/runtime"
USER_DATA_DIR=""
EVENTS_DIR=""
ENGINE_CACHE_DIR="/data/engine-cache"
ENGINE_BUILD=""
DOWNLOAD_DIR="/exchange/downloads"
DISPLAY_NUM=":99"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile-id)
      PROFILE_ID="$2"; shift 2 ;;
    --runtime-instance-id)
      RUNTIME_INSTANCE_ID="$2"; shift 2 ;;
    --config-snapshot)
      CONFIG_SNAPSHOT="$2"; shift 2 ;;
    --run-dir)
      RUN_DIR="$2"; shift 2 ;;
    --user-data-dir)
      USER_DATA_DIR="$2"; shift 2 ;;
    --events-dir)
      EVENTS_DIR="$2"; shift 2 ;;
    --engine-build)
      ENGINE_BUILD="$2"; shift 2 ;;
    --engine-cache-dir)
      ENGINE_CACHE_DIR="$2"; shift 2 ;;
    --download-dir)
      DOWNLOAD_DIR="$2"; shift 2 ;;
    --display)
      DISPLAY_NUM="$2"; shift 2 ;;
    *)
      echo "Unknown runtime argument" >&2; exit 1 ;;
  esac
done

if [[ -z "$PROFILE_ID" || -z "$RUNTIME_INSTANCE_ID" || -z "$CONFIG_SNAPSHOT" ]]; then
  echo "Error: --profile-id, --runtime-instance-id, and --config-snapshot are required" >&2
  exit 1
fi

# Both identities and the snapshot are validated by Python before any mkdir.
if [[ -z "$USER_DATA_DIR" ]]; then
  USER_DATA_DIR="/data/profiles/${PROFILE_ID}/profile"
fi

if [[ -z "$EVENTS_DIR" ]]; then
  EVENTS_DIR="/data/runtime-events/${PROFILE_ID}"
fi

# The page file chooser (GTK) shows uploaded artifacts as a sidebar shortcut.
GTK_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/gtk-3.0"
mkdir -p "$GTK_CONFIG_DIR"
printf 'file:///exchange/uploads Uploads\n' > "$GTK_CONFIG_DIR/bookmarks"

export PROFILE_ID RUNTIME_INSTANCE_ID CONFIG_SNAPSHOT RUN_DIR USER_DATA_DIR
export EVENTS_DIR ENGINE_CACHE_DIR ENGINE_BUILD DOWNLOAD_DIR DISPLAY_NUM

# supervisord owns the two independent processes. No control/RPC socket is
# configured: only the allowlisted Browser Agent is exposed to the caller.
exec python3 - <<'PYTHON'
import configparser
import os
import shlex
from pathlib import Path

from cbrowser.runtime_agent.security import validate_runtime_id
from cbrowser.runtime_agent.runner import load_config_snapshot

validate_runtime_id(os.environ["PROFILE_ID"])
validate_runtime_id(os.environ["RUNTIME_INSTANCE_ID"])
load_config_snapshot(os.environ["PROFILE_ID"], Path(os.environ["CONFIG_SNAPSHOT"]))
run_dir = Path(os.environ["RUN_DIR"])
run_dir.mkdir(parents=True, exist_ok=True)
(run_dir / "runner_info.json").unlink(missing_ok=True)
config = configparser.RawConfigParser()
config["supervisord"] = {
    "nodaemon": "true", "logfile": "/dev/null", "logfile_maxbytes": "0",
    "pidfile": str(run_dir / "supervisord.pid"),
    "childlogdir": str(run_dir),
}
runner = [
    "python3", "-m", "cbrowser.runtime_agent.runner",
    "--profile-id", os.environ["PROFILE_ID"],
    "--runtime-instance-id", os.environ["RUNTIME_INSTANCE_ID"],
    "--config-snapshot", os.environ["CONFIG_SNAPSHOT"],
    "--run-dir", str(run_dir), "--user-data-dir", os.environ["USER_DATA_DIR"],
    "--events-dir", os.environ["EVENTS_DIR"],
    "--engine-cache-dir", os.environ["ENGINE_CACHE_DIR"],
    "--display", os.environ["DISPLAY_NUM"],
]
if os.environ["ENGINE_BUILD"]:
    runner += ["--engine-build", os.environ["ENGINE_BUILD"]]
agent = [
    "python3", "-m", "cbrowser.runtime_agent.agent",
    "--run-dir", str(run_dir), "--events-dir", os.environ["EVENTS_DIR"],
    "--download-dir", os.environ["DOWNLOAD_DIR"],
]
for name, command, restart, priority in [
    ("browser_runner", runner, "false", "10"), ("uds_agent", agent, "true", "20"),
]:
    config["program:" + name] = {
        "command": shlex.join(command).replace("%", "%%"),
        "autostart": "true", "autorestart": restart,
        "startsecs": "0", "startretries": "0", "priority": priority,
        "stopasgroup": "false" if name == "browser_runner" else "true",
        "killasgroup": "true", "stopwaitsecs": "10",
        "stdout_logfile": "/dev/fd/1", "stdout_logfile_maxbytes": "0",
        "stderr_logfile": "/dev/fd/2", "stderr_logfile_maxbytes": "0",
    }
path = run_dir / "processes.conf"
with path.open("w") as target:
    config.write(target)
os.execvp("supervisord", ["supervisord", "-c", str(path)])
PYTHON
