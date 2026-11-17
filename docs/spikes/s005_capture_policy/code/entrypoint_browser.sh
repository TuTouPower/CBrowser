#!/bin/bash
set -e

# Start Xvfb
export DISPLAY=:99
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99
Xvfb :99 -screen 0 1920x1080x24 -listen tcp -ac +extension MIT-SHM +extension XTEST +extension DAMAGE &
XVFB_PID=$!

echo "Waiting for Xvfb..."
for i in {1..30}; do
  if [ -S /tmp/.X11-unix/X99 ]; then
    break
  fi
  sleep 0.1
done

# Start Openbox window manager
openbox &

# Start minimal HTTP server for test page
python3 -m http.server 8099 --directory /test_assets &
HTTP_PID=$!

echo "Starting CloakBrowser on :99..."
# CloakBrowser binary path
CHROME_BIN=$(python3 -c "import cloakbrowser; print(cloakbrowser.binary_info()['binary_path'])")
"$CHROME_BIN" --no-sandbox --disable-dev-shm-usage \
  --window-size=1920,1080 --window-position=0,0 \
  --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 \
  "http://127.0.0.1:8099/test_page.html" &
CHROME_PID=$!

echo "Browser runtime ready with X11 socket at /tmp/.X11-unix/X99"
# Keep alive
wait $CHROME_PID || wait $XVFB_PID
