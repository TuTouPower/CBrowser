#!/usr/bin/env bash
# run_spike.sh - CBrowser v2 Runtime Spike Reproduction Suite (Strict Verification)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="${SCRIPT_DIR}"
LOG_FILE="${WORK_DIR}/reproduce.log"

# Note: Preserving prior logs by appending to reproduce.log
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "=========================================================="
echo " Starting CBrowser v2 Runtime Spike Test Suite (Iteration 2)"
echo " Date: $(date)"
echo " Log file: ${LOG_FILE}"
echo "=========================================================="

PREFIX="cbrowser-spike-runtime"
NET="${PREFIX}-net"
X11_VOL="${PREFIX}-x11-vol"
PULSE_VOL="${PREFIX}-pulse-vol"
BROWSER_CONT="${PREFIX}-browser"
STREAM_CONT="${PREFIX}-stream"

cleanup() {
    echo "[cleanup] Tearing down spike containers, volumes and networks..."
    docker rm -f "${BROWSER_CONT}" "${STREAM_CONT}" >/dev/null 2>&1 || true
    docker volume rm -f "${X11_VOL}" "${PULSE_VOL}" >/dev/null 2>&1 || true
    docker network rm "${NET}" >/dev/null 2>&1 || true
}

trap cleanup EXIT
cleanup

echo "[step 1/6] Reusing / Building test images if not present..."
docker image inspect "${PREFIX}-browser:test" >/dev/null 2>&1 || docker build -t "${PREFIX}-browser:test" -f "${WORK_DIR}/Dockerfile.spike-browser" "${WORK_DIR}"
docker image inspect "${PREFIX}-stream:test" >/dev/null 2>&1 || docker build -t "${PREFIX}-stream:test" -f "${WORK_DIR}/Dockerfile.spike-stream" "${WORK_DIR}"

echo "[step 2/6] Compiling strict MIT-SHM verification tool..."
docker run --rm -v "${WORK_DIR}:/src" "${PREFIX}-stream:test" gcc -O2 /src/test_mitshm.c -lX11 -lXext -o /src/test_mitshm

echo "[step 3/6] Initializing isolated Docker resources..."
docker network create "${NET}"
docker volume create "${X11_VOL}"
docker volume create "${PULSE_VOL}"

echo "[step 4/6] Starting Browser Runtime container (1920x1080 DPR1, PulseAudio, shareable IPC)..."
docker run -d --name "${BROWSER_CONT}" \
  --ipc shareable \
  --network "${NET}" \
  --shm-size 1g \
  -v "${X11_VOL}:/tmp/.X11-unix" \
  -v "${PULSE_VOL}:/pulse-socket" \
  -v "${WORK_DIR}:/app_test" \
  --entrypoint /app_test/entry_browser_full.sh \
  "${PREFIX}-browser:test"

echo "[step 4/6] Waiting for Browser Runtime initialization..."
sleep 6

echo "--- [VERIFY ITEM 01 & 05: CloakBrowser & 1920x1080 Resolution & Real UI Geometry] ---"
# 1) Verify Xvfb screen geometry
docker exec -e DISPLAY=:99 "${BROWSER_CONT}" xdpyinfo | grep -E "dimensions:\s+1920x1080 pixels"
echo "PASS: Xvfb screen geometry verified at 1920x1080."

# 2) Verify CloakBrowser window geometry <= 1920x1080 and inside screen bounds
python3 -c "
import subprocess, re
out = subprocess.check_output(['docker', 'exec', '-e', 'DISPLAY=:99', '${BROWSER_CONT}', 'xwininfo', '-root', '-tree']).decode('utf-8')
print('X11 Window Tree snippet:\n' + '\n'.join([line for line in out.splitlines() if 'Chromium' in line or 'CBrowser' in line]))
match = re.search(r'(0x[0-9a-fA-F]+)\s+\"([^\"]*CBrowser Cloak 1080p[^\"]*)\"', out)
assert match, 'CloakBrowser window with title CBrowser Cloak 1080p not found!'
wid = match.group(1)
win_info = subprocess.check_output(['docker', 'exec', '-e', 'DISPLAY=:99', '${BROWSER_CONT}', 'xwininfo', '-id', wid]).decode('utf-8')
print(f'Window Info for {wid}:\n{win_info}')

w_match = re.search(r'Width:\s+(\d+)', win_info)
h_match = re.search(r'Height:\s+(\d+)', win_info)
x_match = re.search(r'Absolute upper-left X:\s+(-?\d+)', win_info)
y_match = re.search(r'Absolute upper-left Y:\s+(-?\d+)', win_info)

w, h = int(w_match.group(1)), int(h_match.group(1))
x, y = int(x_match.group(1)), int(y_match.group(1))

print(f'Window frame geometry: {w}x{h} at ({x}, {y})')
assert x >= 0 and y >= 0, f'Window out of screen bounds: x={x}, y={y}'
assert w <= 1920 and h <= 1080, f'Window frame exceeds screen dimensions 1920x1080: w={w}, h={h}'
print(f'PASS: Window frame {w}x{h} fits strictly within 1920x1080 screen!')
"

# 3) Check JS / DOM metrics (innerWidth, innerHeight, devicePixelRatio)
docker exec "${BROWSER_CONT}" cat /tmp/cloak_metrics.json
python3 -c "
import json, subprocess
raw_metrics = subprocess.check_output(['docker', 'exec', '${BROWSER_CONT}', 'cat', '/tmp/cloak_metrics.json']).decode('utf-8')
m = json.loads(raw_metrics)
print('DOM Metrics:', m)
assert m['devicePixelRatio'] == 1, f'DPR is not 1: {m[\"devicePixelRatio\"]}'
assert m['innerWidth'] > 1800, f'innerWidth too small: {m[\"innerWidth\"]}'
# Real browser UI (tab bar + address bar) occupies ~70-130px vertically
content_diff = m['outerHeight'] - m['innerHeight']
print(f'Chrome UI height overhead (Tabs/Address bar): {content_diff}px')
assert 50 <= content_diff <= 180, f'Chrome UI height {content_diff}px not within expected range for address/tab bar!'
print('PASS: Real browser UI (tab bar & address bar) verified via DOM metrics and DPR=1.')
"

echo "--- [VERIFY ITEM 03: MIT-SHM Positive Test (Shared IPC)] ---"
docker run --rm \
  --ipc "container:${BROWSER_CONT}" \
  -v "${X11_VOL}:/tmp/.X11-unix" \
  -v "${WORK_DIR}:/app_test" \
  -e DISPLAY=:99 \
  "${PREFIX}-stream:test" /app_test/test_mitshm
echo "PASS: C low-level MIT-SHM positive test completed."

docker run --rm \
  --ipc "container:${BROWSER_CONT}" \
  -v "${X11_VOL}:/tmp/.X11-unix" \
  -e DISPLAY=:99 \
  "${PREFIX}-stream:test" python3 -c "
from pixelflux import ScreenCapture, CaptureSettings
cap = ScreenCapture()
s = CaptureSettings()
frames = []
def cb(buf):
    frames.append(len(buf))
cap.start_capture(cb, s)
import time
time.sleep(1)
cap.stop_capture()
assert len(frames) > 0, 'No frames captured'
print(f'PASS: Pixelflux successfully captured {len(frames)} frames through XShm! First frame: {frames[0]} bytes')
"

echo "--- [VERIFY ITEM 03: MIT-SHM Negative Test (Non-shared IPC)] ---"
docker run --rm \
  -v "${X11_VOL}:/tmp/.X11-unix" \
  -v "${WORK_DIR}:/app_test" \
  -e DISPLAY=:99 \
  "${PREFIX}-stream:test" /app_test/test_mitshm --expect-shm-denied

docker run --rm \
  -v "${X11_VOL}:/tmp/.X11-unix" \
  -e DISPLAY=:99 \
  "${PREFIX}-stream:test" python3 -c "
from pixelflux import ScreenCapture, CaptureSettings
cap = ScreenCapture()
s = CaptureSettings()
def cb(buf): pass
rejected = False
try:
    cap.start_capture(cb, s)
except Exception as e:
    err_str = str(e)
    print('Caught expected pixelflux rejection:', err_str)
    if 'error_code: 10' in err_str or 'Access' in err_str:
        rejected = True
assert rejected, 'Pixelflux should have been rejected by X server due to non-shared IPC!'
print('PASS: Pixelflux XShm attach confirmed rejected by X11 Access check in non-shared IPC!')
"

echo "--- [VERIFY ITEM 04: Cross-Container PCM Audio Sampling (cbrowser_sink.monitor)] ---"
# Check pactl server
docker run --rm \
  -v "${PULSE_VOL}:/pulse-socket" \
  -e PULSE_SERVER=unix:/pulse-socket/pulse-socket \
  "${PREFIX}-stream:test" pactl info | grep -E "Default Sink: cbrowser_sink"

# Generate 440Hz test sine WAV inside browser container
docker exec -e PULSE_SERVER=unix:/pulse-socket/pulse-socket "${BROWSER_CONT}" python3 -c "
import math, struct, wave
with wave.open('/tmp/test_sine.wav', 'wb') as wf:
    wf.setnchannels(2)
    wf.setsampwidth(2)
    wf.setframerate(44100)
    data = bytearray()
    for i in range(44100 * 2):
        val = int(30000.0 * math.sin(2.0 * math.pi * 440.0 * i / 44100.0))
        data.extend(struct.pack('<hh', val, val))
    wf.writeframes(data)
print('Generated /tmp/test_sine.wav (440Hz sine wave)')
"

# Start playing the WAV via paplay loop directly to cbrowser_sink in background
docker exec -d -e PULSE_SERVER=unix:/pulse-socket/pulse-socket "${BROWSER_CONT}" bash -c "while true; do paplay --device=cbrowser_sink /tmp/test_sine.wav; done"

sleep 0.5

# Stream container records PCM from cbrowser_sink.monitor via pulsesrc (strict, no || true)
RECORDED_RAW="${WORK_DIR}/recorded.raw"
rm -f "${RECORDED_RAW}"

docker run --rm \
  -v "${PULSE_VOL}:/pulse-socket" \
  -v "${WORK_DIR}:/app_test" \
  -e PULSE_SERVER=unix:/pulse-socket/pulse-socket \
  "${PREFIX}-stream:test" \
  gst-launch-1.0 pulsesrc device=cbrowser_sink.monitor num-buffers=50 ! "audio/x-raw,format=S16LE,channels=2,rate=44100" ! filesink location=/app_test/recorded.raw

# Analyze recorded PCM file - must exist, size > 0, and contain non-zero audio samples
python3 -c "
import os
raw_file = '${RECORDED_RAW}'
size = os.path.getsize(raw_file)
print(f'Recorded PCM size: {size} bytes')
assert size >= 10000, f'Audio file too small: {size} bytes'
with open(raw_file, 'rb') as f:
    data = f.read()
non_zero = sum(1 for b in data if b != 0)
ratio = (non_zero / size) * 100
print(f'Non-zero bytes: {non_zero}/{size} ({ratio:.1f}%)')
assert non_zero > 10000 and ratio > 50.0, 'Audio recording only captured silence!'
print('PASS: Real audio playback and cross-container PCM sampling verified with continuous non-zero samples!')
"

echo "--- [VERIFY ITEM 02 & 12: Selkies 2.1.0, 127.0.0.1 Binding & UDP Mux] ---"
docker run -d --name "${STREAM_CONT}" \
  --ipc "container:${BROWSER_CONT}" \
  --network "${NET}" \
  -p 127.0.0.1:30005:30005/udp \
  -p 127.0.0.1:18080:8080 \
  -v "${X11_VOL}:/tmp/.X11-unix" \
  -v "${PULSE_VOL}:/pulse-socket" \
  -e DISPLAY=:99 \
  -e PULSE_SERVER=unix:/pulse-socket/pulse-socket \
  "${PREFIX}-stream:test" selkies \
    --addr=0.0.0.0 \
    --mode=webrtc \
    --encoder=h264enc \
    --webrtc-udp-mux-port=30005 \
    --enable-basic-auth=false \
    --enable-resize=false \
    --audio-device-name=cbrowser_sink.monitor \
    --debug=true

sleep 3

# Verify HTTP signaling on 127.0.0.1:18080
curl -sI http://127.0.0.1:18080/ | grep -E "HTTP/1.1 200 OK"
echo "PASS: HTTP signaling listening on 127.0.0.1:18080."

# Verify UDP mux port 30005 is bound in container
docker exec "${STREAM_CONT}" cat /proc/net/udp | grep -iE "7535"
echo "PASS: UDP mux port 30005 socket confirmed bound in container."

# Verify pixelflux 1920x1080 screen capture
docker run --rm \
  --ipc "container:${BROWSER_CONT}" \
  -v "${X11_VOL}:/tmp/.X11-unix" \
  -v "${PULSE_VOL}:/pulse-socket" \
  -v "${WORK_DIR}:/app_test" \
  -e DISPLAY=:99 \
  "${PREFIX}-stream:test" python3 -c "
import pixelflux
png_data = pixelflux.screenshot_png(0)
print('Pixelflux capture PNG size:', len(png_data), 'bytes')
assert len(png_data) > 5000, 'Captured frame too small'
with open('/app_test/screenshot.png', 'wb') as f:
    f.write(png_data)
"
echo "PASS: Screen frame buffer captured via pixelflux (saved to .scratch/runtime_spike/screenshot.png)."

echo "=========================================================="
echo " SPIKE REPRODUCTION RUN FINISHED SUCCESSFULLY!"
echo " Note on Item 12: Real WebRTC client media demux marked NOT_RUN (per instructions)."
echo "=========================================================="
