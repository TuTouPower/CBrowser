import argparse
import asyncio
import json
import logging
import os
import sys
import urllib.parse
from cloakbrowser import launch_persistent_context_async

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("browser_runner")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True, help="Profile ID (A or B)")
    parser.add_argument("--display", default=":91", help="X11 display")
    parser.add_argument("--freq", type=float, default=440.0, help="Audio frequency")
    parser.add_argument("--title", required=True, help="Browser window title")
    parser.add_argument("--bg-color", default="#112233", help="Page background color")
    parser.add_argument("--secret", required=True, help="Profile secret sentinel")
    args = parser.parse_args()

    os.environ["DISPLAY"] = args.display

    # 1. Write sentinel in profile directory
    profile_dir = "/data/profile"
    os.makedirs(profile_dir, exist_ok=True)
    sentinel_path = os.path.join(profile_dir, f"sentinel-{args.profile.lower()}.txt")
    with open(sentinel_path, "w") as f:
        f.write(args.secret + "\n")
    logger.info(f"[browser_runner] Profile {args.profile} sentinel written to {sentinel_path}")

    # 2. Launch CloakBrowser persistent context
    data_dir = os.path.join(profile_dir, "chrome_user_data")
    os.makedirs(data_dir, exist_ok=True)

    browser_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--window-position=0,0",
        "--window-size=1920,1080",
        "--remote-debugging-port=9222",
        "--remote-debugging-address=127.0.0.1",
        "--force-device-scale-factor=1",
        "--autoplay-policy=no-user-gesture-required",
    ]

    logger.info(f"[browser_runner] Launching CloakBrowser on {args.display}...")
    ctx = await launch_persistent_context_async(
        user_data_dir=data_dir,
        headless=False,
        args=browser_args,
        no_viewport=True,
    )
    logger.info(f"[browser_runner] CloakBrowser launched for Profile {args.profile}!")

    page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    # Construct complete HTML with fully encoded data URL to prevent '#' hash truncation
    raw_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{args.title}</title>
  <style>
    body {{
      margin: 0;
      padding: 48px;
      background-color: {args.bg_color};
      color: #ffffff;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }}
    .card {{
      background: rgba(0, 0, 0, 0.45);
      border: 3px solid rgba(255, 255, 255, 0.6);
      border-radius: 12px;
      padding: 32px;
      max-width: 900px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
    }}
    h1 {{
      margin-top: 0;
      font-size: 36px;
      letter-spacing: 0.5px;
    }}
    .badge {{
      display: inline-block;
      background: #ffffff;
      color: #111111;
      padding: 6px 16px;
      font-weight: 800;
      border-radius: 6px;
      font-size: 24px;
    }}
    .field {{
      margin: 16px 0;
      font-size: 20px;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1 id="title-text">{args.title}</h1>
    <div class="field">Profile Identifier: <span id="profile-id" class="badge">{args.profile}</span></div>
    <div class="field">Status: <strong id="status-text">Active, Non-root, Read-only Rootfs</strong></div>
    <div class="field" id="color-box">Target Background: <strong>{args.bg_color}</strong></div>
    <div class="field" id="metrics-box">Target Resolution: 1920x1080 @ 1.0 DPR</div>
  </div>
</body>
</html>"""
    encoded_html = urllib.parse.quote(raw_html)
    data_url = f"data:text/html;charset=utf-8,{encoded_html}"
    await page.goto(data_url)
    logger.info(f"[browser_runner] Navigated to fully encoded fixture page: {args.title} (bg: {args.bg_color})")

    # Start actual CloakBrowser page WebAudio Oscillator (440Hz / 880Hz, gain 0.4)
    audio_info = await page.evaluate(f"""async () => {{
        const targetFreq = {float(args.freq)};
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        window.__audioCtx = new AudioCtx();
        window.__osc = window.__audioCtx.createOscillator();
        window.__gain = window.__audioCtx.createGain();

        window.__osc.type = 'sine';
        window.__osc.frequency.value = targetFreq;
        window.__osc.frequency.setValueAtTime(targetFreq, window.__audioCtx.currentTime);

        window.__gain.gain.value = 0.4;
        window.__gain.gain.setValueAtTime(0.4, window.__audioCtx.currentTime);

        window.__osc.connect(window.__gain);
        window.__gain.connect(window.__audioCtx.destination);

        window.__osc.start();
        if (window.__audioCtx.state !== 'running') {{
            await window.__audioCtx.resume();
        }}
        return {{
            state: window.__audioCtx.state,
            frequency: window.__osc.frequency.value,
            gain: window.__gain.gain.value,
            sampleRate: window.__audioCtx.sampleRate
        }};
    }}""")
    logger.info(f"[browser_runner] CloakBrowser WebAudio started: {audio_info}")
    assert audio_info["state"] == "running", f"AudioContext state is not running: {audio_info['state']}"

    # Real DOM verification: verify background color RGB, profile ID, title
    dom_result = await page.evaluate("""() => {
        const bodyStyle = window.getComputedStyle(document.body);
        const profileEl = document.getElementById('profile-id');
        const titleEl = document.getElementById('title-text');
        const statusEl = document.getElementById('status-text');
        return {
            title: document.title,
            profileIdText: profileEl ? profileEl.innerText.trim() : null,
            titleText: titleEl ? titleEl.innerText.trim() : null,
            statusText: statusEl ? statusEl.innerText.trim() : null,
            backgroundColor: bodyStyle.backgroundColor,
            color: bodyStyle.color,
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            outerWidth: window.outerWidth,
            outerHeight: window.outerHeight,
            devicePixelRatio: window.devicePixelRatio
        };
    }""")

    # Parse hex color to rgb
    hex_clean = args.bg_color.lstrip("#")
    exp_r = int(hex_clean[0:2], 16)
    exp_g = int(hex_clean[2:4], 16)
    exp_b = int(hex_clean[4:6], 16)
    expected_rgb = f"rgb({exp_r}, {exp_g}, {exp_b})"

    logger.info("DOM evaluation result: %s", json.dumps(dom_result))
    assert dom_result["title"] == args.title, f"DOM title mismatch: {dom_result['title']} != {args.title}"
    assert dom_result["profileIdText"] == args.profile, f"DOM profileIdText mismatch: {dom_result['profileIdText']} != {args.profile}"
    assert dom_result["backgroundColor"] == expected_rgb, f"DOM backgroundColor mismatch: {dom_result['backgroundColor']} != {expected_rgb}"
    assert dom_result["backgroundColor"] != "rgba(0, 0, 0, 0)", "DOM backgroundColor is transparent (white/empty)!"
    assert dom_result["backgroundColor"] != "rgb(255, 255, 255)", "DOM backgroundColor is default white!"

    dom_result["expected_rgb"] = expected_rgb
    dom_result["audioContextState"] = audio_info["state"]
    dom_result["audioFrequency"] = audio_info["frequency"]
    dom_result["audioGain"] = audio_info["gain"]
    dom_result["audioSampleRate"] = audio_info["sampleRate"]
    dom_result["audioSource"] = "CloakBrowser WebAudio OscillatorNode"
    with open("/tmp/cloak_metrics.json", "w") as f:
        json.dump(dom_result, f)
    logger.info(f"[browser_runner] DOM metrics, background RGB ({expected_rgb}), and WebAudio state ({audio_info['state']}) verified and written to /tmp/cloak_metrics.json")

    # Keep alive
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
