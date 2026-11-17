#!/bin/bash
set -e

mkdir -p /tmp/.X11-unix /tmp/pulse
chmod 1777 /tmp/.X11-unix /tmp/pulse

# Start default PulseAudio daemon
pulseaudio -D --exit-idle-time=-1
sleep 0.5
# Expose shared unix socket
pactl load-module module-native-protocol-unix auth-anonymous=1 socket=/tmp/pulse/native

# Remove stale locks
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99

# Start Xvfb strictly at 1920x1080x24
Xvfb :99 -screen 0 1920x1080x24 -ac +extension RANDR +extension RENDER +extension MIT-SHM &
XVFB_PID=$!
export DISPLAY=:99
export PULSE_SERVER=unix:/tmp/pulse/native

# Wait for X server
for i in {1..50}; do
    if xset q >/dev/null 2>&1; then
        echo "X server is ready on :99"
        break
    fi
    sleep 0.1
done

# Window Manager
openbox &

# Create test page with audio, video animation, and verifiable input
cat << "EOF" > /tmp/test_page.html
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>CloakBrowser Official Test Page</title>
<style>
  body { margin: 0; background: #0f172a; color: white; font-family: monospace; overflow: hidden; }
  #container { position: absolute; top: 0; left: 0; width: 1920px; height: 1080px; }
  canvas { position: absolute; top: 0; left: 0; width: 1920px; height: 1080px; }
  #ui { position: absolute; top: 30px; left: 40px; z-index: 10; background: rgba(15, 23, 42, 0.85); padding: 25px; border-radius: 12px; border: 2px solid #38bdf8; width: 650px; }
  h1 { margin: 0 0 15px 0; font-size: 32px; color: #38bdf8; }
  input { font-size: 24px; padding: 10px 14px; width: 580px; border-radius: 6px; border: 2px solid #a855f7; background: #1e293b; color: #f8fafc; outline: none; margin-bottom: 15px; }
  .status { font-size: 20px; margin: 6px 0; }
  #input-log { background: #020617; padding: 10px; border-radius: 6px; border: 1px solid #334155; font-size: 18px; word-break: break-all; min-height: 40px; }
</style>
</head>
<body>
<div id="container">
  <canvas id="c" width="1920" height="1080"></canvas>
  <div id="ui">
    <h1>CBrowser v2 Verification Hub</h1>
    <div class="status" id="audio-status">Audio: Initializing...</div>
    <div class="status" id="frame-status">Frame: 0</div>
    <input id="spike-input" autofocus placeholder="Target input for WebRTC clients..." />
    <div><strong>Input Value Content:</strong></div>
    <div id="input-log"></div>
  </div>
</div>
<script>
  const canvas = document.getElementById('c');
  const ctx = canvas.getContext('2d');
  const inputEl = document.getElementById('spike-input');
  const inputLogEl = document.getElementById('input-log');
  const frameStatusEl = document.getElementById('frame-status');
  const audioStatusEl = document.getElementById('audio-status');

  // Input event tracking
  inputEl.addEventListener('input', () => {
    inputLogEl.innerText = inputEl.value;
  });

  window.addEventListener('load', () => inputEl.focus());
  document.addEventListener('click', () => inputEl.focus());

  // Web Audio continuous non-silent 440Hz sine wave tone
  let actx = null;
  function startAudio() {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      actx = new AudioCtx();
      const osc = actx.createOscillator();
      const gain = actx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(440, actx.currentTime);
      gain.gain.setValueAtTime(0.4, actx.currentTime);
      osc.connect(gain);
      gain.connect(actx.destination);
      osc.start();
      audioStatusEl.innerText = 'Audio: Active 440Hz Sine Wave (Non-Silent, ' + actx.state + ')';
    } catch(e) {
      audioStatusEl.innerText = 'Audio Error: ' + e.message;
    }
  }
  startAudio();
  document.addEventListener('visibilitychange', () => {
    if (actx && actx.state === 'suspended') actx.resume();
  });

  // High dynamic animation rendering loop (1920x1080)
  let frame = 0;
  function render(time) {
    frame++;
    ctx.fillStyle = '#090d16';
    ctx.fillRect(0, 0, 1920, 1080);

    const t = time / 1000;
    const cx = 960, cy = 540;
    for (let i = 0; i < 24; i++) {
      const angle = t * 1.8 + (i * Math.PI / 12);
      const r = 320 + Math.sin(t * 3.0 + i) * 80;
      ctx.beginPath();
      ctx.arc(cx + Math.cos(angle) * r, cy + Math.sin(angle) * r, 28, 0, Math.PI * 2);
      ctx.fillStyle = `hsl(${(i * 15 + t * 50) % 360}, 90%, 65%)`;
      ctx.fill();
    }

    ctx.fillStyle = '#38bdf8';
    ctx.font = 'bold 36px monospace';
    ctx.fillText('Resolution: 1920x1080 Fixed Canvas', 80, 420);
    ctx.font = '28px monospace';
    ctx.fillText('Frame: ' + frame + ' | Time: ' + t.toFixed(2) + 's', 80, 470);
    ctx.fillText('Live Input: [' + inputEl.value + ']', 80, 520);

    frameStatusEl.innerText = 'Frame: ' + frame;
    inputLogEl.innerText = inputEl.value;
    requestAnimationFrame(render);
  }
  requestAnimationFrame(render);
</script>
</body>
</html>
EOF

CHROME_BIN=$(ls -d /root/.cloakbrowser/chromium-*/chrome | head -n 1)
echo "Starting CloakBrowser ($CHROME_BIN) with CDP enabled only on 127.0.0.1:9222..."

$CHROME_BIN \
  --no-sandbox \
  --disable-gpu \
  --disable-dev-shm-usage \
  --window-size=1920,1080 \
  --window-position=0,0 \
  --autoplay-policy=no-user-gesture-required \
  --no-first-run \
  --no-default-browser-check \
  --remote-debugging-port=9222 \
  --remote-debugging-address=127.0.0.1 \
  file:///tmp/test_page.html &

CHROME_PID=$!
echo "CloakBrowser started PID: $CHROME_PID"

trap "kill -TERM $CHROME_PID $XVFB_PID; exit 0" SIGINT SIGTERM
wait $CHROME_PID
