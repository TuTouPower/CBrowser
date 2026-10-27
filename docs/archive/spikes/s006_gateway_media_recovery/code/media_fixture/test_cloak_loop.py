import asyncio
import json
import os
import sys
from cloakbrowser import launch_persistent_context_async

async def main():
    display = os.environ.get("DISPLAY", ":99")
    print(f"[test_cloak_loop] Starting CloakBrowser window on {display} (1920x1080 screen)...")
    data_dir = "/tmp/cloak_test_profile_1080p"
    os.makedirs(data_dir, exist_ok=True)

    # Launch args:
    # Do NOT pass --kiosk or --start-fullscreen (we want real tabs & address bar!)
    # Do NOT fix content viewport (viewport=None or no_viewport=True)
    # We pass --window-position=0,0 and --window-size=1920,1080 or let Openbox maximize it within 1920x1080
    args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--window-position=0,0",
        "--window-size=1920,1080",
        "--remote-debugging-port=9222",
        "--remote-debugging-address=127.0.0.1",
        "--force-device-scale-factor=1",
    ]

    context = await launch_persistent_context_async(
        user_data_dir=data_dir,
        headless=False,
        args=args,
        no_viewport=True, # Preserve true browser window layout (address bar, tab bar)
    )
    print("[test_cloak_loop] Browser window launched with no_viewport=True!")
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto("data:text/html,<html><head><title>CBrowser Cloak 1080p</title></head><body style='background:%23224466;color:white;font-family:sans-serif;'><h1>CBrowser Cloak 1920x1080 Verified</h1><p>Real browser UI with Address bar & Tabs visible.</p></body></html>")
    print("[test_cloak_loop] Navigation complete.")

    # Record innerWidth, innerHeight, devicePixelRatio from page execution
    metrics = await page.evaluate("""() => {
        return {
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            outerWidth: window.outerWidth,
            outerHeight: window.outerHeight,
            devicePixelRatio: window.devicePixelRatio
        };
    }""")
    print("[test_cloak_loop] Page DOM Metrics:", json.dumps(metrics))
    with open("/tmp/cloak_metrics.json", "w") as f:
        json.dump(metrics, f)

    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
