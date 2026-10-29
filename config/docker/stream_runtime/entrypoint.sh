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
export SELKIES_MANUAL_RESOLUTION=true
export SELKIES_MANUAL_WIDTH=1920
export SELKIES_MANUAL_HEIGHT=1080
export SELKIES_FRAMERATE="8,8-30"
export SELKIES_VIDEO_STREAMING_MODE=false
export SELKIES_WEBRTC_UDP_MUX_PORT="${CBROWSER_UDP_MUX_PORT:-30006}"
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
  --manual-width 1920 \
  --manual-height 1080 \
  --audio-device-name "$SELKIES_AUDIO_DEVICE_NAME" \
  --webrtc-udp-mux-port "$SELKIES_WEBRTC_UDP_MUX_PORT" \
  --webrtc-public-ip "$SELKIES_WEBRTC_PUBLIC_IP" \
  --addr 127.0.0.1 \
  --port "$SELKIES_PORT" \
  --framerate "8,8-30"
