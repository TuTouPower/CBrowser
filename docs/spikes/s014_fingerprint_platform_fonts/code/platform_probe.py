"""s014: does CloakBrowser 0.6.4 / Chromium 146 keep navigator.platform, UA and
UA Client Hints consistent for --fingerprint-platform=windows / macos?

Runs inside the Linux arm64 probe container with the real Chromium 146 engine
mounted read-only. No product code is modified. This is the first half of the
spike; font visibility is measured separately once font sets exist.
"""

from __future__ import annotations

import http.server
import json
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ENGINE = "/data/engine-cache/chromium-146.0.7680.177.3/chrome"


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = b"<!doctype html><title>probe</title><body>platform-probe</body>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


def _serve():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server

BASIC_JS = """() => ({
  platform: navigator.platform,
  userAgent: navigator.userAgent,
  appVersion: navigator.appVersion,
  uaDataPlatform: navigator.userAgentData ? navigator.userAgentData.platform : null,
  uaDataBrands: navigator.userAgentData ? navigator.userAgentData.brands : null,
  uaDataMobile: navigator.userAgentData ? navigator.userAgentData.mobile : null,
  languages: navigator.languages,
})"""

HIGH_ENTROPY_JS = """async () => {
  if (!navigator.userAgentData || !navigator.userAgentData.getHighEntropyValues) {
    return null;
  }
  try {
    return await navigator.userAgentData.getHighEntropyValues([
      "platform", "platformVersion", "architecture", "bitness", "model",
    ]);
  } catch (e) {
    return {error: String(e)};
  }
}"""


def probe(platform: str, origin: str) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=ENGINE,
            headless=True,
            args=["--no-sandbox", f"--fingerprint-platform={platform}"],
        )
        try:
            page = browser.new_page()
            page.goto(origin, wait_until="domcontentloaded", timeout=15000)
            basic = page.evaluate(BASIC_JS)
            high_entropy = page.evaluate(HIGH_ENTROPY_JS)
            return {
                "platform": platform,
                "origin": origin,
                "isSecureContext": page.evaluate("() => isSecureContext"),
                "basic": basic,
                "highEntropy": high_entropy,
            }
        finally:
            browser.close()


def main() -> None:
    print(json.dumps({"engine": ENGINE, "exists": Path(ENGINE).is_file()}))
    server = _serve()
    origin = f"http://127.0.0.1:{server.server_address[1]}/"
    print(json.dumps({"origin": origin}))
    try:
        for platform in ("windows", "macos"):
            try:
                print(json.dumps(probe(platform, origin), ensure_ascii=False))
            except Exception as exc:  # noqa: BLE001 - probe diagnostics
                print(
                    json.dumps(
                        {"platform": platform, "error": f"{type(exc).__name__}: {exc}"},
                        ensure_ascii=False,
                    )
                )
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
