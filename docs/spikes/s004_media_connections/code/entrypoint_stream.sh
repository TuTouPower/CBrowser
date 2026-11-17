#!/bin/bash
set -e

export DISPLAY=:99
export PULSE_SERVER=unix:/tmp/pulse/native

# Wait for X11 socket
for i in {1..60}; do
    if [ -S /tmp/.X11-unix/X99 ]; then
        echo "X11 socket detected at /tmp/.X11-unix/X99"
        break
    fi
    sleep 0.2
done

# Wait for PulseAudio socket
for i in {1..60}; do
    if [ -S /tmp/pulse/native ]; then
        echo "Pulse socket detected at /tmp/pulse/native"
        break
    fi
    sleep 0.2
done

echo "Starting Selkies 2.1.0 WebRTC Server with fixed 1920x1080 resolution and audio capture..."
exec selkies \
  --mode webrtc \
  --enable-basic-auth=false \
  --enable-sharing=true \
  --enable-collab=false \
  --enable-resize=false \
  --manual-width 1920 \
  --manual-height 1080 \
  --audio-device-name auto_null.monitor \
  --webrtc-udp-mux-port 30006 \
  --webrtc-public-ip 127.0.0.1 \
  --addr 0.0.0.0 \
  --port 18081 \
  --framerate 8,8-30
