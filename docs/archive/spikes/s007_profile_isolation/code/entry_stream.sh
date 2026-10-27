#!/bin/bash
set -euo pipefail

DISPLAY_NUM="${1:-:91}"
PROFILE_ID="${2:-A}"

echo "[entry_stream] Starting Stream container for Profile $PROFILE_ID on Display $DISPLAY_NUM..."

COOKIE_HEX_FILE="/tmp/.X11-unix/cookie.hex"
for i in {1..30}; do
    if [ -f "$COOKIE_HEX_FILE" ]; then
        break
    fi
    sleep 0.2
done

if [ ! -f "$COOKIE_HEX_FILE" ]; then
    echo "FAIL: cookie.hex not found in /tmp/.X11-unix"
    exit 1
fi

RAW_COOKIE=$(cat "$COOKIE_HEX_FILE")
STREAM_XAUTH="/tmp/stream_xauth"
touch "$STREAM_XAUTH"
xauth -q -f "$STREAM_XAUTH" add "$DISPLAY_NUM" . "$RAW_COOKIE"
chmod 600 "$STREAM_XAUTH"

export DISPLAY="$DISPLAY_NUM"
export XAUTHORITY="$STREAM_XAUTH"
export PULSE_SERVER="unix:/pulse/pulse.sock"
export PULSE_COOKIE="/pulse/pulse.cookie"

echo "[entry_stream] Stream container initialized and ready."
tail -f /dev/null
