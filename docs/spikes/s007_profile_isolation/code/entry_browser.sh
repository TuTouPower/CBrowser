#!/bin/bash
set -euo pipefail

PROFILE_ID="${1:-A}"
DISPLAY_NUM="${2:-:91}"
FREQ="${3:-440.0}"
TITLE="${4:-CBrowser Profile $PROFILE_ID}"
BG_COLOR="${5:-#112233}"
SECRET="${6:-PROFILE_${PROFILE_ID}_DEFAULT_SECRET}"

echo "[entry_browser] Initializing Browser container for Profile $PROFILE_ID (Display $DISPLAY_NUM)..."

# Ensure dirs exist in tmp / pulse
mkdir -p /tmp/pulse-runtime /tmp/pulse-config /tmp/openbox

# 1. PulseAudio setup
PULSE_COOKIE_PATH="/pulse/pulse.cookie"
PULSE_SOCK_PATH="/pulse/pulse.sock"

# Generate 256-byte random binary cookie
dd if=/dev/urandom of="$PULSE_COOKIE_PATH" bs=256 count=1 2>/dev/null
chmod 644 "$PULSE_COOKIE_PATH"

# Align PulseAudio hardware sample rate to 48000Hz to match CloakBrowser WebAudio internal clock
cat << 'EOF' > /tmp/pulse-config/daemon.conf
default-sample-rate = 48000
alternate-sample-rate = 48000
EOF

cat << EOF > /tmp/pulse.pa
load-module module-native-protocol-unix auth-anonymous=0 auth-cookie=$PULSE_COOKIE_PATH socket=$PULSE_SOCK_PATH
load-module module-null-sink sink_name=cbrowser_sink rate=48000 format=s16le channels=2 sink_properties=device.description="CBrowser_Virtual_Sink"
set-default-sink cbrowser_sink
EOF

export PULSE_CONFIG_PATH=/tmp/pulse-config
pulseaudio --system=false --daemonize=yes --fail=yes --file=/tmp/pulse.pa -n
sleep 1
echo "[entry_browser] PulseAudio daemon started with strict cookie auth and native 48000Hz sample rate."

# 2. X11 & Xvfb setup
MCOOKIE=$(mcookie)
echo "$MCOOKIE" > /tmp/.X11-unix/cookie.hex
chmod 644 /tmp/.X11-unix/cookie.hex

XAUTH_PATH="/tmp/.X11-unix/Xauthority"
touch "$XAUTH_PATH"
xauth -q -f "$XAUTH_PATH" add "$DISPLAY_NUM" . "$MCOOKIE"
chmod 644 "$XAUTH_PATH"

Xvfb "$DISPLAY_NUM" -auth "$XAUTH_PATH" -screen 0 1920x1080x24 -dpi 96 +extension MIT-SHM +extension XTEST +extension XFIXES -nolisten tcp &
XVFB_PID=$!
echo "[entry_browser] Xvfb started on $DISPLAY_NUM (pid $XVFB_PID)"

# Wait for X11 socket
SOCKET_PATH="/tmp/.X11-unix/X${DISPLAY_NUM#:}"
for i in {1..30}; do
    if [ -S "$SOCKET_PATH" ]; then
        echo "[entry_browser] X11 socket $SOCKET_PATH is ready."
        break
    fi
    sleep 0.2
done

export DISPLAY="$DISPLAY_NUM"
export XAUTHORITY="$XAUTH_PATH"
export PULSE_SERVER="unix:$PULSE_SOCK_PATH"
export PULSE_COOKIE="$PULSE_COOKIE_PATH"

# 3. Openbox setup
cat << EOF > /tmp/openbox/rc.xml
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <resistance>
    <strength>10</strength>
    <screen_edge_strength>20</screen_edge_strength>
  </resistance>
  <applications>
    <application class="*">
      <maximized>yes</maximized>
      <decor>yes</decor>
    </application>
  </applications>
</openbox_config>
EOF

openbox --config-file /tmp/openbox/rc.xml &
OPENBOX_PID=$!
echo "[entry_browser] Openbox started (pid $OPENBOX_PID)"
sleep 1

# 4. Launch CloakBrowser & Audio runner
python3 /app_probe/browser_runner.py \
    --profile "$PROFILE_ID" \
    --display "$DISPLAY_NUM" \
    --freq "$FREQ" \
    --title "$TITLE" \
    --bg-color "$BG_COLOR" \
    --secret "$SECRET" &
RUNNER_PID=$!
echo "[entry_browser] Browser runner started (pid $RUNNER_PID)"

# 5. Window maximize watcher
(
  for i in {1..30}; do
    WID=$(xdotool search --onlyvisible --class "chromium-browser" 2>/dev/null | head -n 1 || true)
    if [ -n "$WID" ]; then
      xdotool windowsize "$WID" 1920 1080 2>/dev/null || true
      xdotool windowmove "$WID" 0 0 2>/dev/null || true
      echo "[entry_browser] Maximized window $WID to 1920x1080."
      break
    fi
    sleep 0.5
  done
) &

# Flag ready
touch /tmp/ready.flag
echo "[entry_browser] Profile $PROFILE_ID initialization complete. READY."

tail -f /dev/null
