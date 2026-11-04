"""Core library for the t029 automation compatibility probe.

The probe answers three questions with field-level evidence, for the
exact pinned toolchain of this repository:

1. What can a real Playwright process do through the production
   ``cbat_`` API -> Supervisor -> Agent UDS -> Chrome tunnel, and which
   CDP commands does its attach emit that mutate shared browser state?
2. On the target engine (the ``cloakbrowser`` package's linux-x64
   CloakBrowser binary, production launch args, fixed seed/config/
   viewport, headed under Xvfb), what do automation levels L1-L6 add on
   top of the L0 production baseline, field by field?
3. How do CDP Input and XTEST input compare, and what is the native
   JavaScript Dialog baseline (pending commands, orphaned dialogs,
   beforeunload activation)?

ego-lite is a design reference only: the public harness at the pinned
baseline commit ``12407167f84a58af24044f072868051952131491`` was read for
its snapshot/ref and dialog failure cases.  Its browser binary and the
``globalThis.ego`` native bindings are closed source, are not a runtime
dependency here, and no result in this probe is an ego or CloakBrowser
fingerprint verdict.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import shutil
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

PLAYWRIGHT_VERSION = "1.64.1"
CLOAKBROWSER_PACKAGE_VERSION = "0.6.4"
TARGET_ENGINE_VERSION = "146.0.7680.177.5"
EGO_LITE_BASELINE_COMMIT = "12407167f84a58af24044f072868051952131491"
REPORT_SCHEMA = "automation-probe-report/v1"

#: A level field counts as a *new change* only when a value outside the
#: full L0 sample set recurs in at least this fraction of the level's
#: samples (AC-004 pre-registered threshold: >= 4 of 5).
NEW_CHANGE_MIN_FRACTION = 0.8


class ProbePrerequisiteMissing(RuntimeError):
    """A cloud prerequisite (engine binary, XTEST, browser) is absent."""


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


# ---------------------------------------------------------------------------
# Self-hosted observation pages
# ---------------------------------------------------------------------------

_MAIN_HTML = """<!doctype html>
<title>CBrowser Probe Main</title>
<h1>Probe Main</h1>
<button id="popup-btn" type="button">Open popup</button>
<a id="download-link" href="/download">Download probe file</a>
<input id="text-input" type="text" autocomplete="off">
<div id="pad" style="width:300px;height:180px;background:#446688">Pointer pad</div>
<div id="scrollbox" style="width:320px;height:120px;overflow:auto;border:1px solid #000">
  <div style="height:600px;padding-top:420px">
    <button id="scroll-target" type="button">Scroll target</button>
  </div>
</div>
<label><input id="bu-toggle" type="checkbox"> Arm beforeunload</label>
<button id="alert-btn" type="button">Alert</button>
<button id="confirm-btn" type="button">Confirm</button>
<button id="prompt-btn" type="button">Prompt</button>
<iframe id="frame" src="/frame" width="340" height="200"></iframe>
<script>
window.__events = [];
window.__lastDialog = null;
function record(ev) {
  window.__events.push({
    type: ev.type,
    isTrusted: ev.isTrusted,
    clientX: ev.clientX, clientY: ev.clientY,
    screenX: ev.screenX, screenY: ev.screenY,
    movementX: ev.movementX || 0, movementY: ev.movementY || 0,
    pointerType: ev.pointerType || null,
    button: ev.button, buttons: ev.buttons,
    deltaY: ev.deltaY || 0, key: ev.key || null,
    timeStamp: Math.round(ev.timeStamp * 1000) / 1000,
    target: ev.target && ev.target.id ? ev.target.id : String(ev.target)
  });
}
for (const name of ["pointerdown","pointerup","pointermove","mousedown","mouseup","click","wheel","keydown","keyup"]) {
  document.getElementById("pad").addEventListener(name, record);
  document.getElementById("text-input").addEventListener(name, record);
}
document.getElementById("scrollbox").addEventListener("wheel", record);
document.getElementById("popup-btn").addEventListener("click", () => {
  window.open("/popup", "_blank", "width=320,height=200");
});
document.getElementById("alert-btn").addEventListener("click", () => {
  alert("probe-alert");
  window.__lastDialog = {type: "alert", result: "closed"};
});
document.getElementById("confirm-btn").addEventListener("click", () => {
  const result = confirm("probe-confirm");
  window.__lastDialog = {type: "confirm", result};
});
document.getElementById("prompt-btn").addEventListener("click", () => {
  const result = prompt("probe-prompt", "default-text");
  window.__lastDialog = {type: "prompt", result};
});
document.getElementById("bu-toggle").addEventListener("change", (ev) => {
  if (ev.target.checked) {
    window.onbeforeunload = (e) => { e.preventDefault(); e.returnValue = ""; };
  } else {
    window.onbeforeunload = null;
  }
});
</script>
"""

_FRAME_HTML = """<!doctype html>
<title>CBrowser Probe Frame</title>
<h2>Probe Frame</h2>
<div id="frame-pad" style="width:200px;height:100px;background:#884466">Frame pad</div>
<input id="frame-input" type="text" autocomplete="off">
<script>
window.__events = [];
for (const name of ["pointerdown","pointerup","click","keydown"]) {
  document.getElementById("frame-pad").addEventListener(name, (ev) => {
    window.__events.push({type: ev.type, isTrusted: ev.isTrusted,
      clientX: ev.clientX, clientY: ev.clientY,
      screenX: ev.screenX, screenY: ev.screenY,
      pointerType: ev.pointerType || null, target: ev.target.id});
  });
  document.getElementById("frame-input").addEventListener(name, (ev) => {
    window.__events.push({type: ev.type, isTrusted: ev.isTrusted,
      key: ev.key || null, target: ev.target.id});
  });
}
</script>
"""

_POPUP_HTML = "<!doctype html><title>CBrowser Probe Popup</title><h1>Probe Popup</h1>\n"
_OTHER_HTML = "<!doctype html><title>CBrowser Probe Other</title><h1>Probe Other</h1>\n"

_DOWNLOAD_BODY = b"cbrowser-probe-download\n"


class ObservationServer:
    """Loopback-only HTTP server for the self-hosted observation pages."""

    def __init__(self) -> None:
        pages = {
            "/": _MAIN_HTML,
            "/frame": _FRAME_HTML,
            "/popup": _POPUP_HTML,
            "/other": _OTHER_HTML,
        }

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # silence test noise
                pass

            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                path = self.path.split("?", 1)[0]
                if path == "/download":
                    self.send_response(200)
                    self.send_header(
                        "Content-Disposition",
                        'attachment; filename="probe-download.txt"',
                    )
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(_DOWNLOAD_BODY)))
                    self.end_headers()
                    self.wfile.write(_DOWNLOAD_BODY)
                    return
                body = pages.get(path)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                raw = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> "ObservationServer":
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._server.shutdown()
        self._server.server_close()


#: Page-side signal collection.  Every field is JSON-native and stable
#: across repeated loads of the same engine/seed/config; volatile values
#: (timestamps, ports, random ids) are deliberately excluded.
SIGNAL_SCRIPT = r"""() => {
  const nav = navigator;
  const gl = document.createElement('canvas').getContext('webgl');
  let glVendor = null, glRenderer = null;
  if (gl) {
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    glVendor = ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR);
    glRenderer = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
  }
  const cnv = document.createElement('canvas');
  cnv.width = 220; cnv.height = 40;
  const cx = cnv.getContext('2d');
  cx.font = '16px Arial'; cx.fillStyle = '#123456';
  cx.fillText('cbrowser-probe', 4, 20); cx.fillRect(120, 4, 60, 24);
  const data = cnv.toDataURL();
  let hash = 0x811c9dc5;
  for (let i = 0; i < data.length; i++) {
    hash ^= data.charCodeAt(i); hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  const leakNames = ['__playwright', '__pwInitScripts', '__cdc',
    'cdc_adoQpoasnfa76pfcZLmcfl_Array', '__webdriver_evaluate',
    '__driver_evaluate', '__selenium_evaluate', 'callPhantom', '_phantom',
    '__nightmare', 'domAutomation', 'domAutomationController', '__utils__'];
  return {
    userAgent: nav.userAgent,
    platform: nav.platform,
    language: nav.language,
    languages: Array.from(nav.languages || []),
    hardwareConcurrency: nav.hardwareConcurrency,
    deviceMemory: nav.deviceMemory === undefined ? null : nav.deviceMemory,
    webdriver: nav.webdriver,
    maxTouchPoints: nav.maxTouchPoints,
    vendor: nav.vendor,
    cookieEnabled: nav.cookieEnabled,
    pdfViewerEnabled: nav.pdfViewerEnabled === undefined ? null : nav.pdfViewerEnabled,
    uaBrands: nav.userAgentData ? nav.userAgentData.brands.map(b => b.brand + '/' + b.version).join(',') : null,
    screenWidth: screen.width, screenHeight: screen.height,
    availWidth: screen.availWidth, availHeight: screen.availHeight,
    colorDepth: screen.colorDepth,
    devicePixelRatio: window.devicePixelRatio,
    innerWidth: window.innerWidth, innerHeight: window.innerHeight,
    outerWidth: window.outerWidth, outerHeight: window.outerHeight,
    hasFocus: document.hasFocus(),
    visibilityState: document.visibilityState,
    pointerFine: matchMedia('(pointer: fine)').matches,
    hoverHover: matchMedia('(hover: hover)').matches,
    prefersDark: matchMedia('(prefers-color-scheme: dark)').matches,
    prefersReducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    plugins: nav.plugins.length, mimeTypes: nav.mimeTypes.length,
    webglVendor: glVendor, webglRenderer: glRenderer,
    canvasHash: ('00000000' + hash.toString(16)).slice(-8),
    globalLeaks: leakNames.filter((name) => name in window)
  };
}"""

READ_EVENTS_SCRIPT = "() => { const e = window.__events || []; window.__events = []; return e; }"


# ---------------------------------------------------------------------------
# Sample comparison (AC-004 pre-registered rule)
# ---------------------------------------------------------------------------


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def compare_level_samples(
    baseline_samples: list[dict[str, Any]],
    level_samples: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return field-level new changes of one level against the L0 samples.

    A field is listed when some value that never occurs in any L0 sample
    recurs in at least ``NEW_CHANGE_MIN_FRACTION`` of the level samples.
    """
    if not baseline_samples or not level_samples:
        return []
    threshold = max(1, math.ceil(len(level_samples) * NEW_CHANGE_MIN_FRACTION))
    fields: set[str] = set()
    for sample in baseline_samples + level_samples:
        fields.update(sample.keys())
    changes: list[dict[str, Any]] = []
    for field in sorted(fields):
        baseline_values = {_canonical(s.get(field)) for s in baseline_samples}
        outside: dict[str, tuple[Any, int]] = {}
        for sample in level_samples:
            key = _canonical(sample.get(field))
            if key not in baseline_values:
                value, count = outside.get(key, (sample.get(field), 0))
                outside[key] = (value, count + 1)
        for value, count in outside.values():
            if count >= threshold:
                changes.append(
                    {
                        "field": field,
                        "baseline_values": sorted(
                            json.loads(v) for v in baseline_values
                        ),
                        "new_value": value,
                        "occurrences": count,
                        "samples": len(level_samples),
                    }
                )
    return changes


def summarize_levels(
    samples_by_level: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """Per-level verdicts: no_change / new_changes / insufficient."""
    baseline = samples_by_level.get("L0", [])
    summary: dict[str, dict[str, Any]] = {}
    for level in sorted(samples_by_level):
        samples = samples_by_level[level]
        if level == "L0":
            summary[level] = {"verdict": "baseline", "samples": len(samples)}
            continue
        if len(samples) < 5 or len(baseline) < 5:
            summary[level] = {
                "verdict": "insufficient",
                "samples": len(samples),
                "reason": "fewer than 5 samples on the level or on L0",
            }
            continue
        changes = compare_level_samples(baseline, samples)
        summary[level] = {
            "verdict": "new_changes" if changes else "no_change",
            "samples": len(samples),
            "changes": changes,
        }
    return summary


# ---------------------------------------------------------------------------
# CDP command classification (AC-002 / t030 intercept list)
# ---------------------------------------------------------------------------

_CLOSE_METHODS = {"Browser.close", "Target.closeTarget", "Page.close"}
_DOWNLOAD_METHODS = {"Browser.setDownloadBehavior", "Page.setDownloadBehavior"}
_EMULATION_PREFIXES = ("Emulation.set", "Emulation.clear")
_INPUT_PREFIXES = ("Input.",)
_EVALUATION_METHODS = {"Runtime.evaluate", "Runtime.callFunctionOn"}
_NAVIGATION_METHODS = {"Page.navigate", "Page.reload", "Page.navigateToHistoryEntry"}
_INJECTION_METHODS = {"Page.addScriptToEvaluateOnNewDocument"}
_ATTACH_METHODS = {"Target.setAutoAttach"}


def classify_cdp_method(method: str) -> str:
    """Classify one CDP method by its effect on shared browser state."""
    if method in _CLOSE_METHODS:
        return "closes_shared_state"
    if method in _DOWNLOAD_METHODS:
        return "download_policy"
    if method in _INJECTION_METHODS:
        return "script_injection"
    if method in _ATTACH_METHODS:
        return "target_attach"
    if method.startswith(_EMULATION_PREFIXES):
        return "emulation_override"
    if method.endswith(".enable"):
        return "domain_enable"
    if method.startswith(_INPUT_PREFIXES):
        return "input_dispatch"
    if method in _EVALUATION_METHODS:
        return "page_evaluation"
    if method in _NAVIGATION_METHODS:
        return "navigation"
    return "other"


#: Commands t030 must intercept or mediate rather than forward blindly.
MUST_MEDIATE_METHODS = sorted(
    _CLOSE_METHODS
    | _DOWNLOAD_METHODS
    | {
        "Emulation.setUserAgentOverride",
        "Emulation.setGeolocationOverride",
        "Emulation.setDeviceMetricsOverride",
        "Emulation.setTouchEmulationEnabled",
        "Emulation.setEmulatedMedia",
        "Emulation.setFocusEmulationEnabled",
        "Network.emulateNetworkConditions",
        "Page.addScriptToEvaluateOnNewDocument",
    }
)


# ---------------------------------------------------------------------------
# Report hygiene
# ---------------------------------------------------------------------------

_SECRET_KEY_TOKENS = {
    "token",
    "password",
    "passwd",
    "secret",
    "authorization",
    "cookie",
    "credential",
    "apikey",
}
_BEARER_RE = re.compile(r"Bearer\s+\S+")
_CBAT_RE = re.compile(r"cbat_[A-Za-z0-9_\-]+")
_HOME_RE = re.compile(re.escape(str(Path.home())))
_KEY_SPLIT_RE = re.compile(r"[^a-z0-9]+")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _is_secret_key(key: Any) -> bool:
    """True when a dict key names a credential, by whole token.

    Tokenising (snake/kebab/camel boundaries) keeps innocuous signal
    fields such as ``cookieEnabled`` intact — there the sensitive word
    is only the head of a longer descriptive name — while still
    catching ``session_cookie``, ``authToken`` or a bare ``token``.
    """
    spaced = _CAMEL_RE.sub(" ", str(key)).lower()
    tokens = [t for t in _KEY_SPLIT_RE.split(spaced) if t]
    if not tokens:
        return False
    # Singular/plural normalisation: "cookies" -> "cookie", "api_keys"
    # -> [api, key]. A bare "key" is an ordinary event field, so it only
    # counts when preceded by api/private.
    norm = [t[:-1] if len(t) > 1 and t.endswith("s") else t for t in tokens]
    if "apikey" in norm or (len(norm) >= 2 and norm[-2] in ("api", "private") and norm[-1] == "key"):
        return True
    if len(norm) == 1:
        return norm[0] in _SECRET_KEY_TOKENS
    return any(t in _SECRET_KEY_TOKENS for t in norm[1:])


def redact_report_value(value: Any) -> Any:
    """Recursively redact credentials and machine-local absolute paths."""
    if isinstance(value, dict):
        return {
            key: (
                "<redacted>"
                if _is_secret_key(key)
                else redact_report_value(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_report_value(item) for item in value]
    if isinstance(value, str):
        text = _BEARER_RE.sub("Bearer <redacted>", value)
        text = _CBAT_RE.sub("cbat_<redacted>", text)
        return _HOME_RE.sub("~", text)
    return value


def build_report(**sections: Any) -> dict[str, Any]:
    """Assemble a schema-tagged, redacted probe report."""
    report = {
        "schema": REPORT_SCHEMA,
        "toolchain": {
            "playwright": PLAYWRIGHT_VERSION,
            "cloakbrowser_package": CLOAKBROWSER_PACKAGE_VERSION,
            "target_engine": TARGET_ENGINE_VERSION,
            "ego_lite_reference_commit": EGO_LITE_BASELINE_COMMIT,
        },
        "threshold": {
            "new_change_min_fraction": NEW_CHANGE_MIN_FRACTION,
            "min_samples_per_level": 5,
        },
        "must_mediate_methods": MUST_MEDIATE_METHODS,
        **sections,
    }
    return redact_report_value(report)


# ---------------------------------------------------------------------------
# XTEST input (xte from the xautomation package)
# ---------------------------------------------------------------------------


class XTestInput:
    """Minimal XTEST driver over the ``xte`` binary (scratch-extractable).

    Coordinates are absolute X11 screen pixels.  The caller owns the
    CSS-to-screen mapping (window position + chrome content offset +
    DPR) and records the mapping it used in the probe report.
    """

    def __init__(
        self,
        display: str,
        xte_path: str | None = None,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ) -> None:
        resolved = xte_path or shutil.which("xte")
        if not resolved:
            raise ProbePrerequisiteMissing(
                "xte binary not found (xautomation package); XTEST probe cannot run"
            )
        self._xte = resolved
        self._display = display
        self._runner = runner

    def _send(self, *commands: str) -> None:
        env = dict(os.environ, DISPLAY=self._display)
        result = self._runner(
            [self._xte],
            input="\n".join(commands) + "\n",
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"xte failed: {result.stderr.strip()}")

    def move(self, x: int, y: int) -> None:
        self._send(f"mousemove {int(x)} {int(y)}")

    def click(self, x: int, y: int, button: int = 1) -> None:
        self._send(
            f"mousemove {int(x)} {int(y)}", f"mousedown {button}", f"mouseup {button}"
        )

    def key(self, key: str) -> None:
        self._send(f"key {key}")

    def type_text(self, text: str) -> None:
        self._send(f"str {text}")

    def scroll(self, x: int, y: int, steps: int) -> None:
        button = 4 if steps > 0 else 5
        commands = [f"mousemove {int(x)} {int(y)}"] + [
            f"mouseclick {button}" for _ in range(abs(steps))
        ]
        self._send(*commands)


# ---------------------------------------------------------------------------
# Recording bridge: Playwright discovery + WS relay with a command log
# ---------------------------------------------------------------------------


class CdpBridge:
    """Client-side relay between a Playwright process and a CDP endpoint.

    Playwright's ``connect_over_cdp`` needs an HTTP discovery endpoint;
    the production automation tunnel is a bare WebSocket.  The bridge
    serves ``/json/version`` + ``/json/list`` on loopback pointing at its
    own relay socket, then forwards every frame to the real upstream
    (the authenticated API tunnel in chain mode, or the browser's own
    loopback DevTools socket in direct mode) while recording method
    names, event names and response ids.  Payload bodies are not kept.
    """

    def __init__(self, upstream_ws_url: str, headers: dict[str, str] | None = None):
        self._upstream = upstream_ws_url
        self._headers = headers or {}
        self.log: list[dict[str, Any]] = []
        self.trace: list[str] = []
        self.relay_error: str | None = None
        self._id_methods: dict[int, str] = {}
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._ws_port = 0
        self._http: ThreadingHTTPServer | None = None
        self._started = threading.Event()

    # -- lifecycle ------------------------------------------------------
    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())
        self._loop.run_forever()

    async def _serve(self) -> None:
        import websockets

        server = await websockets.serve(self._relay, "127.0.0.1", 0)
        self._ws_port = int(server.sockets[0].getsockname()[1])
        self._started.set()

    def start(self) -> "CdpBridge":
        self._thread.start()
        if not self._started.wait(timeout=10):
            raise RuntimeError("CdpBridge websocket server did not start")
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
                ws_url = f"ws://127.0.0.1:{bridge._ws_port}/cdp"
                if self.path.startswith("/json/version"):
                    payload: Any = {
                        "Browser": "CBrowserProbeBridge",
                        "webSocketDebuggerUrl": ws_url,
                    }
                elif self.path.startswith("/json/list"):
                    payload = [
                        {
                            "id": "probe-page",
                            "type": "page",
                            "title": "CBrowser Probe",
                            "url": "about:blank",
                            "webSocketDebuggerUrl": ws_url,
                        }
                    ]
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self._http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._http.serve_forever, daemon=True).start()
        return self

    @property
    def endpoint_url(self) -> str:
        assert self._http is not None
        return f"http://127.0.0.1:{self._http.server_address[1]}"

    @property
    def ws_url(self) -> str:
        """Direct WebSocket URL of the relay (raw-CDP clients)."""
        return f"ws://127.0.0.1:{self._ws_port}/cdp"

    def close(self) -> None:
        if self._http is not None:
            self._http.shutdown()
            self._http.server_close()
        self._loop.call_soon_threadsafe(self._loop.stop)

    # -- relay ----------------------------------------------------------
    async def _relay(self, client: Any) -> None:
        import websockets

        try:
            upstream = await websockets.connect(
                self._upstream,
                additional_headers=self._headers,
                max_size=32 * 1024 * 1024,
                proxy=None,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced via relay_error
            self.relay_error = f"upstream connect: {type(exc).__name__}: {exc}"
            raise
        async with upstream:
            self.trace.append("upstream connected")

            async def client_to_upstream() -> None:
                async for raw in client:
                    self.trace.append(f"client->upstream {str(raw)[:80]}")
                    self._record("client", raw)
                    await upstream.send(raw)
                self.trace.append("client stream ended")

            async def upstream_to_client() -> None:
                async for raw in upstream:
                    self.trace.append(f"upstream->client {str(raw)[:80]}")
                    self._record("upstream", raw)
                    await client.send(raw)
                self.trace.append("upstream stream ended")

            tasks = [
                asyncio.create_task(client_to_upstream()),
                asyncio.create_task(upstream_to_client()),
            ]
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                if task.exception() is not None:
                    self.relay_error = (
                        f"relay pump: {type(task.exception()).__name__}: "
                        f"{task.exception()}"
                    )
                    self.trace.append(f"pump error: {self.relay_error}")
            for task in pending:
                task.cancel()

    def _record(self, direction: str, raw: Any) -> None:
        try:
            message = json.loads(raw)
        except (ValueError, TypeError):
            return
        if direction == "client" and "method" in message:
            entry: dict[str, Any] = {
                "direction": "client",
                "method": message["method"],
                "category": classify_cdp_method(str(message["method"])),
            }
            if "sessionId" in message:
                entry["session"] = True
            if isinstance(message.get("id"), int):
                self._id_methods[int(message["id"])] = str(message["method"])
            self.log.append(entry)
        elif direction == "upstream" and "method" in message:
            self.log.append({"direction": "upstream", "event": message["method"]})
        elif direction == "upstream" and "id" in message:
            method = self._id_methods.pop(int(message["id"]), None)
            self.log.append(
                {
                    "direction": "upstream",
                    "response_for": method,
                    "error": "error" in message,
                }
            )

    # -- queries --------------------------------------------------------
    def client_methods(self) -> list[str]:
        return [e["method"] for e in self.log if e.get("direction") == "client"]

    def state_changing_methods(self) -> list[dict[str, Any]]:
        """Client commands that mutate shared browser state, in order."""
        seen: list[dict[str, Any]] = []
        for entry in self.log:
            if entry.get("direction") != "client":
                continue
            if entry["category"] in {
                "closes_shared_state",
                "download_policy",
                "script_injection",
                "target_attach",
                "emulation_override",
                "domain_enable",
                "navigation",
            }:
                seen.append(
                    {"method": entry["method"], "category": entry["category"]}
                )
        return seen


# ---------------------------------------------------------------------------
# Host-side BrowserRunner (production launch path, host Xvfb only)
# ---------------------------------------------------------------------------


def host_runner_class() -> type:
    """BrowserRunner with Pulse/Openbox/window-sizing replaced for hosts.

    The production container supplies PulseAudio, Openbox and xdotool;
    the cloud host does not.  Everything else — engine resolution,
    production launch args, the CloakBrowser SDK persistent-context
    launch, runner_info publication and exit observation — is the real
    ``BrowserRunner.start`` code path.
    """
    from cbrowser.runtime_agent.runner import BrowserRunner

    class HostBrowserRunner(BrowserRunner):
        def setup_pulse(self) -> tuple[Path, Path]:
            self.pulse_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            cookie = self.pulse_dir / "pulse.cookie"
            if not cookie.exists() or cookie.stat().st_size != 256:
                cookie.write_bytes(os.urandom(256))
            cookie.chmod(0o600)
            return self.pulse_dir / "pulse.sock", cookie

        def setup_display(self, width: int = 1920, height: int = 1080) -> Path:
            self.xauth_path.touch(mode=0o600, exist_ok=True)
            self.xvfb_proc = subprocess.Popen(
                [
                    "Xvfb",
                    self.display,
                    "-screen",
                    "0",
                    f"{width}x{height}x24",
                    "-dpi",
                    "96",
                    "+extension",
                    "MIT-SHM",
                    "+extension",
                    "XTEST",
                    "+extension",
                    "XFIXES",
                    "-nolisten",
                    "tcp",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            sock = Path(f"/tmp/.X11-unix/X{self.display.lstrip(':')}")
            for _ in range(100):
                if sock.exists():
                    return self.xauth_path
                threading.Event().wait(0.05)
            raise RuntimeError(f"Xvfb did not create {sock}")

        async def _configure_window(self, width: int, height: int) -> None:
            return None

    return HostBrowserRunner


def write_profile_snapshot(
    root: Path,
    *,
    profile_id: str,
    seed: int,
    width: int = 1280,
    height: int = 800,
) -> Path:
    """Write the immutable config snapshot BrowserRunner consumes."""
    snapshot = {
        "id": f"snap-{profile_id}",
        "profile_id": profile_id,
        "version": 1,
        "config": {
            "name": f"Probe {profile_id}",
            "fingerprint_seed": seed,
            "screen_width": width,
            "screen_height": height,
            "timezone": "UTC",
            "locale": "en-US",
            "geoip": False,
            "humanize": False,
            "set_google_default": False,
            "restore_session": False,
            "color_scheme": "light",
        },
        "created_at": "2026-11-04T00:00:00+08:00",
    }
    path = root / "snapshot.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    return path


def engine_cache_dir() -> Path | None:
    """Locate a CloakBrowser engine cache (env override or default)."""
    candidates = []
    override = os.environ.get("CBROWSER_T029_ENGINE_CACHE")
    if override:
        candidates.append(Path(override))
    candidates.append(Path.home() / ".cache" / "cloakbrowser")
    for candidate in candidates:
        binary = candidate / f"chromium-{TARGET_ENGINE_VERSION}" / "chrome"
        if binary.is_file() and os.access(binary, os.X_OK):
            return candidate
    return None


def chromium_executable() -> Path | None:
    """Locate the Playwright-downloaded full Chromium (not headless shell)."""
    roots = []
    override = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if override:
        roots.append(Path(override))
    roots.append(Path.home() / ".cache" / "ms-playwright")
    for root in roots:
        for candidate in sorted(root.glob("chromium-*/chrome-linux64/chrome")):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
    return None


def devtools_ws_url(user_data_dir: Path, timeout: float = 30.0) -> str:
    """Read the browser-level DevTools WS URL from DevToolsActivePort.

    Headed Chromium under a bare Xvfb (no window manager) does not
    publish its DevTools HTTP endpoint when launched as a raw process —
    measured 50 s without a listener — while the Playwright-driven
    launch (the same mechanism the production runner's SDK uses) comes
    up reliably.  Probe browsers are therefore always launched through
    Playwright persistent contexts with ``--remote-debugging-port=0``
    and discovered through this file.
    """
    import urllib.request

    port_file = user_data_dir / "DevToolsActivePort"
    deadline = threading.Event()
    for _ in range(int(timeout * 10)):
        if port_file.exists():
            try:
                port = int(port_file.read_text().splitlines()[0])
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({})
                )
                with opener.open(
                    f"http://127.0.0.1:{port}/json/version", timeout=2.0
                ) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                return str(payload["webSocketDebuggerUrl"])
            except Exception:  # noqa: BLE001 - poll until DevTools is ready
                pass
        deadline.wait(0.1)
    raise RuntimeError("DevToolsActivePort did not become ready")


def find_browser_pid(user_data_dir: Path) -> int | None:
    """Find the main browser process for a persistent user data dir."""
    marker = f"--user-data-dir={user_data_dir}"
    for proc_dir in Path("/proc").glob("[0-9]*"):
        try:
            cmdline = (proc_dir / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        args = [part.decode("utf-8", "replace") for part in cmdline if part]
        if marker in args and not any(a.startswith("--type=") for a in args):
            return int(proc_dir.name)
    return None


def start_xvfb(display: str, width: int = 1280, height: int = 800) -> subprocess.Popen:
    """Start a bare Xvfb with the XTEST extension for probe browsers."""
    proc = subprocess.Popen(
        [
            "Xvfb",
            display,
            "-screen",
            "0",
            f"{width}x{height}x24",
            "-dpi",
            "96",
            "+extension",
            "MIT-SHM",
            "+extension",
            "XTEST",
            "+extension",
            "XFIXES",
            "-nolisten",
            "tcp",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    sock = Path(f"/tmp/.X11-unix/X{display.lstrip(':')}")
    for _ in range(100):
        if sock.exists():
            return proc
        threading.Event().wait(0.05)
    proc.terminate()
    raise RuntimeError(f"Xvfb did not create {sock}")
