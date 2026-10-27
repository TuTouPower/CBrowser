#!/bin/bash
set -euo pipefail

echo "[browser] Starting setup (1920x1080)..."
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99

# Configure and start PulseAudio
mkdir -p /pulse-socket ~/.config/pulse ~/.config/openbox
chmod 777 /pulse-socket
cat << 'PULSE_EOF' > /tmp/pulse-default.pa
load-module module-native-protocol-unix auth-anonymous=1 socket=/pulse-socket/pulse-socket
load-module module-null-sink sink_name=cbrowser_sink sink_properties=device.description="CBrowser_Virtual_Sink"
set-default-sink cbrowser_sink
PULSE_EOF

pulseaudio --system=false --daemonize=no --fail=yes --file=/tmp/pulse-default.pa -n &
PULSE_PID=$!
echo "[browser] PulseAudio started (pid $PULSE_PID)"

# Configure Openbox rc.xml to maximize all windows and ensure they stay within screen
cat << 'RC_EOF' > ~/.config/openbox/rc.xml
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
RC_EOF

# Start Xvfb with MIT-SHM, XTEST at 1920x1080x24 (DPR=1, 96 DPI)
Xvfb :99 -screen 0 1920x1080x24 -dpi 96 +extension MIT-SHM +extension XTEST +extension XFIXES -nolisten tcp &
XVFB_PID=$!
echo "[browser] Xvfb started at 1920x1080x24 (pid $XVFB_PID)"

# Wait for X11 socket
for i in {1..30}; do
    if [ -S /tmp/.X11-unix/X99 ]; then
        echo "[browser] X11 socket ready"
        break
    fi
    sleep 0.2
done

export DISPLAY=:99
export PULSE_SERVER=unix:/pulse-socket/pulse-socket

# Start Openbox
openbox --config-file ~/.config/openbox/rc.xml &
OPENBOX_PID=$!
echo "[browser] Openbox started (pid $OPENBOX_PID)"

sleep 1

# Launch CloakBrowser persistent window in background
python3 /app_test/test_cloak_loop.py &
CLOAK_PID=$!
echo "[browser] CloakBrowser launched (pid $CLOAK_PID)"

# Watch for window and ensure it is maximized within 1920x1080
(
  for i in {1..30}; do
    WID=$(xdotool search --onlyvisible --class "chromium-browser" 2>/dev/null | head -n 1 || true)
    if [ -n "$WID" ]; then
      xdotool windowsize "$WID" 1920 1080 2>/dev/null || true
      xdotool windowmove "$WID" 0 0 2>/dev/null || true
      break
    fi
    sleep 0.5
  done
) &

# Keep alive
tail -f /dev/null
