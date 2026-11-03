#!/bin/bash
set -euo pipefail

# Fail-fast validation of required startup configuration
if [ -z "${CBROWSER_PROFILE_ID:-}" ]; then
    echo "CONFIG_ERROR: CBROWSER_PROFILE_ID is required" >&2
    exit 1
fi

if [ -z "${CBROWSER_RUNTIME_INSTANCE_ID:-}" ]; then
    echo "CONFIG_ERROR: CBROWSER_RUNTIME_INSTANCE_ID is required" >&2
    exit 1
fi

if [ -z "${CBROWSER_GATEWAY_URL:-}" ]; then
    echo "CONFIG_ERROR: CBROWSER_GATEWAY_URL is required" >&2
    exit 1
fi

if [ -z "${CBROWSER_CONFIG_VERSION:-}" ]; then
    echo "CONFIG_ERROR: CBROWSER_CONFIG_VERSION is required" >&2
    exit 1
fi

SCREEN_WIDTH="${CBROWSER_SCREEN_WIDTH:-}"
SCREEN_HEIGHT="${CBROWSER_SCREEN_HEIGHT:-}"
if [ -n "${CBROWSER_SELKIES_CREDENTIALS_FILE:-}" ]; then
    if [ -z "$SCREEN_WIDTH" ] || [ -z "$SCREEN_HEIGHT" ]; then
        echo "CONFIG_ERROR: CBROWSER_SCREEN_WIDTH and CBROWSER_SCREEN_HEIGHT are required" >&2
        exit 1
    fi
fi

SELKIES_WEBRTC_PUBLIC_IP="${CBROWSER_WEBRTC_PUBLIC_IP:-}"
if [ -z "$SELKIES_WEBRTC_PUBLIC_IP" ]; then
    echo "CONFIG_ERROR: CBROWSER_WEBRTC_PUBLIC_IP is required by Supervisor" >&2
    exit 1
fi

# Secret validation: explicit secret file or environment secret
if [ -n "${CBROWSER_AGENT_SECRET_FILE:-}" ]; then
    if [ ! -f "$CBROWSER_AGENT_SECRET_FILE" ] || [ ! -s "$CBROWSER_AGENT_SECRET_FILE" ]; then
        echo "CONFIG_ERROR: CBROWSER_AGENT_SECRET_FILE is missing or empty" >&2
        exit 1
    fi
elif [ -z "${CBROWSER_AGENT_TOKEN:-}" ]; then
    echo "CONFIG_ERROR: Authentication secret required" >&2
    exit 1
fi

# Selkies secure mode: Supervisor mounts a 0600 credentials file (master +
# controller) per Profile. When none is mounted the entrypoint generates
# per-start random tokens itself, so secure mode is never disabled.
SELKIES_CRED_FILE="${CBROWSER_SELKIES_CREDENTIALS_FILE:-/tmp/selkies_credentials.json}"
SELKIES_TOKENS_FILE="${SELKIES_TOKENS_FILE:-/tmp/selkies_tokens.json}"
export SELKIES_TOKENS_FILE

SELKIES_MASTER_TOKEN_FILE="$(mktemp /tmp/.selkies_master.XXXXXX)"
python3 - "$SELKIES_CRED_FILE" "$SELKIES_TOKENS_FILE" \
    "$SELKIES_MASTER_TOKEN_FILE" <<'PY'
import json
import os
import secrets
import sys

cred_path, tokens_path, master_path = sys.argv[1:4]
if os.path.isfile(cred_path) and os.path.getsize(cred_path) > 0:
    with open(cred_path, encoding="utf-8") as handle:
        credentials = json.load(handle)
    master_token = credentials["master_token"]
    controller_token = credentials["controller_token"]
else:
    master_token = secrets.token_urlsafe(32)
    controller_token = secrets.token_urlsafe(32)
    descriptor = os.open(cred_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(
            {
                "master_token": master_token,
                "controller_token": controller_token,
            },
            output,
        )
    os.chmod(cred_path, 0o600)

table = {controller_token: {"role": "controller", "slot": None, "mk_control": False}}
descriptor = os.open(tokens_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as tokens:
    json.dump(table, tokens)
os.chmod(tokens_path, 0o600)

descriptor = os.open(master_path, os.O_WRONLY | os.O_TRUNC, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as output:
    output.write(master_token)
os.chmod(master_path, 0o600)
PY
SELKIES_MASTER_TOKEN="$(cat "$SELKIES_MASTER_TOKEN_FILE")"
export SELKIES_MASTER_TOKEN
rm -f "$SELKIES_MASTER_TOKEN_FILE"
export CBROWSER_SELKIES_CREDENTIALS_FILE="$SELKIES_CRED_FILE"

# Bounded wait for X11 socket
X11_SOCK="${CBROWSER_X11_SOCKET:-/tmp/.X11-unix/X99}"
X11_FOUND=0
for i in {1..50}; do
    if [ -S "$X11_SOCK" ]; then
        X11_FOUND=1
        break
    fi
    sleep 0.2
done
if [ "$X11_FOUND" -ne 1 ]; then
    echo "BOUNDARY_ERROR: X11 socket not detected after bounded wait" >&2
    exit 1
fi

# Standalone/test launches without Supervisor-provided geometry read the real
# Xvfb screen size instead of falling back to a hardcoded default.
if [ -z "$SCREEN_WIDTH" ] || [ -z "$SCREEN_HEIGHT" ]; then
    X11_DIMENSIONS="$(DISPLAY="${DISPLAY:-:99}" XAUTHORITY="${XAUTHORITY:-/tmp/.Xauthority}" xdpyinfo | awk '/dimensions:/ {if (!found) {print $2; found=1}}')"
    SCREEN_WIDTH="${X11_DIMENSIONS%x*}"
    SCREEN_HEIGHT="${X11_DIMENSIONS#*x}"
fi
if ! [[ "$SCREEN_WIDTH" =~ ^[0-9]+$ && "$SCREEN_HEIGHT" =~ ^[0-9]+$ ]] \
    || [ "$SCREEN_WIDTH" -lt 100 ] || [ "$SCREEN_WIDTH" -gt 10000 ] \
    || [ "$SCREEN_HEIGHT" -lt 100 ] || [ "$SCREEN_HEIGHT" -gt 10000 ]; then
    echo "CONFIG_ERROR: valid screen geometry is required" >&2
    exit 1
fi

# Bounded wait for PulseAudio socket (pulse.sock only)
PULSE_DIR="${CBROWSER_PULSE_DIR:-/pulse}"
PULSE_SOCK="$PULSE_DIR/pulse.sock"
PULSE_FOUND=0
for i in {1..50}; do
    if [ -S "$PULSE_SOCK" ]; then
        PULSE_FOUND=1
        break
    fi
    sleep 0.2
done
if [ "$PULSE_FOUND" -ne 1 ]; then
    echo "BOUNDARY_ERROR: PulseAudio socket not detected after bounded wait" >&2
    exit 1
fi

# Check for Pulse cookie
COOKIE_FILE="${PULSE_COOKIE:-$PULSE_DIR/pulse.cookie}"
if [ ! -f "$COOKIE_FILE" ]; then
    echo "BOUNDARY_ERROR: PulseAudio cookie missing" >&2
    exit 1
fi

# Check for Xauthority file
XAUTH_FILE="${XAUTHORITY:-/tmp/.Xauthority}"
if [ ! -f "$XAUTH_FILE" ]; then
    echo "BOUNDARY_ERROR: Xauthority missing" >&2
    exit 1
fi

# Verify runtime mount security boundaries via python boundary checker
python3 -c "from cbrowser.stream_agent.boundary import verify_stream_runtime_boundaries; verify_stream_runtime_boundaries()"

# Configure Selkies environment
export DISPLAY="${DISPLAY:-:99}"
export PULSE_SERVER="unix:$PULSE_SOCK"
export PULSE_COOKIE="$COOKIE_FILE"
export XAUTHORITY="$XAUTH_FILE"

export SELKIES_MODE=webrtc
export SELKIES_ENABLE_BASIC_AUTH=false
export SELKIES_ENABLE_SHARING=true
export SELKIES_ENABLE_COLLAB=false
export SELKIES_ENABLE_RESIZE=false
export SELKIES_ENABLE_DUAL_MODE=false
export SELKIES_FILE_TRANSFERS=none
export SELKIES_ENABLE_CLIPBOARD="${SELKIES_ENABLE_CLIPBOARD:-true}"
export SELKIES_ENABLE_BINARY_CLIPBOARD="${SELKIES_ENABLE_BINARY_CLIPBOARD:-false|locked}"
export SELKIES_CLIPBOARD_SEAMLESS="${SELKIES_CLIPBOARD_SEAMLESS:-true|locked}"
export SELKIES_MANUAL_RESOLUTION=true
# The Agent registers the same geometry Selkies captures.
export CBROWSER_SCREEN_WIDTH="$SCREEN_WIDTH"
export CBROWSER_SCREEN_HEIGHT="$SCREEN_HEIGHT"
export SELKIES_MANUAL_WIDTH="$SCREEN_WIDTH"
export SELKIES_MANUAL_HEIGHT="$SCREEN_HEIGHT"
export SELKIES_FRAMERATE="8,8-30"
export SELKIES_VIDEO_STREAMING_MODE=false
export SELKIES_WEBRTC_UDP_MUX_PORT="${CBROWSER_UDP_MUX_PORT:-30006}"
# ADR 013 / t019: same-machine media uses only 127.0.0.1 host candidates.
# ICE-lite keeps Selkies from falling back to its default external
# STUN/TURN (OpenRelay), whose allocation timeout stalled every new
# PeerConnection for ~5s.
export SELKIES_WEBRTC_ICE_LITE=true
export SELKIES_WEBRTC_PUBLIC_IP="$SELKIES_WEBRTC_PUBLIC_IP"
export SELKIES_AUDIO_DEVICE_NAME="${CBROWSER_AUDIO_DEVICE:-cbrowser_sink.monitor}"
export SELKIES_PORT="${SELKIES_PORT:-18081}"
export SELKIES_ADDR="127.0.0.1"

# Launch StreamAgent with patched WebRTCService
exec python3 -m cbrowser.stream_agent.agent \
  --mode webrtc \
  --enable-basic-auth=false \
  --enable-sharing=true \
  --enable-collab=false \
  --enable-resize=false \
  --enable-dual-mode=false \
  --file-transfers=none \
  --enable-clipboard "$SELKIES_ENABLE_CLIPBOARD" \
  --enable-binary-clipboard "$SELKIES_ENABLE_BINARY_CLIPBOARD" \
  --clipboard-seamless "$SELKIES_CLIPBOARD_SEAMLESS" \
  --tokens-file "$SELKIES_TOKENS_FILE" \
  --manual-width "$SCREEN_WIDTH" \
  --manual-height "$SCREEN_HEIGHT" \
  --audio-device-name "$SELKIES_AUDIO_DEVICE_NAME" \
  --webrtc-udp-mux-port "$SELKIES_WEBRTC_UDP_MUX_PORT" \
  --webrtc-ice-lite \
  --webrtc-public-ip "$SELKIES_WEBRTC_PUBLIC_IP" \
  --addr 127.0.0.1 \
  --port "$SELKIES_PORT" \
  --framerate "8,8-30"
