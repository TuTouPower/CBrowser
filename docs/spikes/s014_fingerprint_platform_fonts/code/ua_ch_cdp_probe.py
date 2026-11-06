"""s014: does CDP Emulation.setUserAgentOverride (userAgentMetadata) cover every
context? Measures main document, same-origin iframe, dedicated Worker,
ServiceWorker-controlled fetch and Sec-CH-UA-Arch request headers.

No product code is modified.
"""

from __future__ import annotations

import http.server
import json
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ENGINE = "/data/engine-cache/chromium-146.0.7680.177.3/chrome"
ACCEPT_CH = "Sec-CH-UA-Arch, Sec-CH-UA-Bitness, Sec-CH-UA-Platform-Version, Sec-CH-UA-Platform"
CAPTURED: list[dict] = []

MAIN = b"""<!doctype html><title>cdp</title><body><iframe src="/iframe"></iframe>
<script>
window.results = [];
const he = async () => {
  if (!navigator.userAgentData) return {none: true};
  return await navigator.userAgentData.getHighEntropyValues(
    ['architecture','bitness','platform','platformVersion']);
};
window.addEventListener('message', e => { window.results.push(e.data); });
(async () => {
  window.mainHE = await he();
  const blob = new Blob([`
    (async () => {
      const d = self.navigator.userAgentData;
      const v = d ? await d.getHighEntropyValues(['architecture','bitness','platform','platformVersion']) : {none:true};
      self.postMessage({ctx:'worker', he:v});
    })();
  `], {type:'text/javascript'});
  const w = new Worker(URL.createObjectURL(blob));
  w.onmessage = e => window.results.push(e.data);
  try {
    const reg = await navigator.serviceWorker.register('/sw.js');
    await navigator.serviceWorker.ready;
    window.swReady = !!reg.active;
  } catch (e) { window.swReady = String(e); }
  await fetch('/probe');
})();
</script></body>"""

IFRAME = b"""<!doctype html><title>iframe</title><script>
(async () => {
  const d = navigator.userAgentData;
  const v = d ? await d.getHighEntropyValues(['architecture','bitness','platform','platformVersion']) : {none:true};
  parent.postMessage({ctx:'iframe', he:v}, '*');
})();
</script>"""

SW = b"""self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => {
  if (e.request.url.indexOf('/sw-probe') !== -1) {
    e.respondWith((async () => {
      const d = self.navigator.userAgentData;
      const v = d ? await d.getHighEntropyValues(
        ['architecture','bitness','platform','platformVersion']) : {none:true};
      return new Response(JSON.stringify({ctx:'serviceworker', he:v,
        ua:self.navigator.userAgent}),
        {headers:{'Content-Type':'application/json'}});
    })());
  }
});
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        CAPTURED.append(
            {
                "path": self.path,
                "ch": {
                    k: v for k, v in self.headers.items()
                    if k.lower().startswith("sec-ch-ua")
                },
                "ua": self.headers.get("User-Agent"),
            }
        )
        if self.path.startswith("/iframe"):
            body = IFRAME
        elif self.path.startswith("/sw.js"):
            body = SW
        elif self.path.startswith("/"):
            body = MAIN if self.path == "/" else b"ok"
        else:
            body = b"ok"
        self.send_response(200)
        ctype = (
            "application/javascript"
            if self.path.startswith("/sw.js")
            else "text/html; charset=utf-8"
        )
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-CH", ACCEPT_CH)
        self.send_header("Critical-CH", ACCEPT_CH)
        self.send_header("Service-Worker-Allowed", "/")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


def override(session) -> None:
    session.send(
        "Emulation.setUserAgentOverride",
        {
            "userAgent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
            ),
            "platform": "Win32",
            "userAgentMetadata": {
                "brands": [
                    {"brand": "Chromium", "version": "146"},
                    {"brand": "Not-A.Brand", "version": "24"},
                    {"brand": "Google Chrome", "version": "146"},
                ],
                "fullVersionList": [
                    {"brand": "Chromium", "version": "146.0.0.0"},
                    {"brand": "Not-A.Brand", "version": "24.0.0.0"},
                    {"brand": "Google Chrome", "version": "146.0.0.0"},
                ],
                "fullVersion": "146.0.0.0",
                "platform": "Windows",
                "platformVersion": "19.0.0",
                "architecture": "x86",
                "bitness": "64",
                "model": "",
                "mobile": False,
            },
        },
    )


def main() -> None:
    print(json.dumps({"engine": ENGINE, "exists": Path(ENGINE).is_file()}))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{server.server_address[1]}/"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=ENGINE,
                headless=True,
                args=["--no-sandbox", "--fingerprint-platform=windows"],
            )
            try:
                context = browser.new_context(service_workers="allow")
                page = context.new_page()
                session = context.new_cdp_session(page)
                override(session)
                CAPTURED.clear()
                page.goto(origin, wait_until="load", timeout=20000)
                page.wait_for_timeout(1500)
                main_he = page.evaluate("() => window.mainHE")
                results = page.evaluate("() => window.results")
                sw_ready = page.evaluate("() => window.swReady")
                try:
                    sw_payload = page.evaluate(
                        "() => fetch('/sw-probe').then(r => r.json())"
                    )
                    page.wait_for_timeout(400)
                    results.append(sw_payload)
                except Exception as exc:  # noqa: BLE001
                    results.append({"ctx": "serviceworker", "error": str(exc)})
                print(
                    json.dumps(
                        {
                            "mainHE": main_he,
                            "contexts": results,
                            "swReady": sw_ready,
                            "requests": list(CAPTURED),
                        },
                        ensure_ascii=False,
                    )
                )
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
