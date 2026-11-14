#!/bin/bash
set -euo pipefail

# t065: the Supervisor starts this container with the gated entrypoint,
# which execs this script with the forwarder command as arguments
# (python3 -m cbrowser.proxy_forwarder --config ... --listen-host ...).
# The command itself validates the mounted credentials file and fails
# closed before the listen socket opens, so this script only forwards.
if [ "$#" -eq 0 ]; then
    echo "CONFIG_ERROR: forwarder command is required" >&2
    exit 1
fi

exec "$@"
