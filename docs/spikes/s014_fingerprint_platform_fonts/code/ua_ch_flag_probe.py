"""s014: is there an engine-level switch controlling UA-CH architecture/bitness?

Launches the real Chromium 146 once per candidate flag set and reports
getHighEntropyValues() plus the Sec-CH-UA-* request headers the server sees
after an Accept-CH response. No product code is modified.
"""

from __future__ import annotations

import http.server
import json
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ENGINE = "/data/engine-cache/chromium-146.0.7680.177.3/chrome"
ACCEPT_CH = ", ".join(
    ["Sec-CH-UA-Arch", "Sec-CH-UA-Bitness", "Sec-CH-UA-Platform", "Sec-CH-UA-Platform-Version"]
)
CAPTURED: list[dict] = []
PAGE = b"""<!doctype html><title>ua-ch</title><body>
<script>fetch('/probe').then(r => r.text())</script>
</body>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        CAPTURED.append(
            {
                "path": self.path,
                "headers": {
                    k: v
                    for k, v in self.headers.items()
                    if k.lower().startswith("sec-ch-ua") or k.lower() == "user-agent"
                },
            }
        )
        body = PAGE if self.path == "/" else b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Accept-CH", ACCEPT_CH)
        self.send_header("Critical-CH", ACCEPT_CH)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


HE_JS = """async () => {
  if (!navigator.userAgentData || !navigator.userAgentData.getHighEntropyValues) return null;
  return await navigator.userAgentData.getHighEntropyValues(
    ['architecture', 'bitness', 'platform', 'platformVersion', 'model']);
}"""

CANDIDATES = [
    ("control", []),
    ("fingerprint-arch", ["--fingerprint-arch=x86"]),
    ("fingerprint-architecture", ["--fingerprint-architecture=x86"]),
    ("ch-ua-arch", ["--ch-ua-arch=x86"]),
    ("force-ua-ch-arch", ["--force-ua-ch-arch=x86"]),
    ("fp-combo", ["--fingerprint-arch=x86", "--fingerprint-bitness=64"]),
]


def run(origin: str, name: str, extra: list[str]) -> dict:
    CAPTURED.clear()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=ENGINE,
            headless=True,
            args=["--no-sandbox", "--fingerprint-platform=windows", *extra],
        )
        try:
            page = browser.new_page()
            page.goto(origin, wait_until="load", timeout=15000)
            page.wait_for_timeout(400)
            he = page.evaluate(HE_JS)
            return {"case": name, "extra": extra, "highEntropy": he, "requests": list(CAPTURED)}
        except Exception as exc:  # noqa: BLE001
            return {"case": name, "extra": extra, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            browser.close()


def main() -> None:
    print(json.dumps({"engine": ENGINE, "exists": Path(ENGINE).is_file()}))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{server.server_address[1]}/"
    try:
        for name, extra in CANDIDATES:
            print(json.dumps(run(origin, name, extra), ensure_ascii=False))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
