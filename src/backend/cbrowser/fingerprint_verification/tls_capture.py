"""Local controlled TLS ClientHello capture (JA3 / JA4) and 4-context HTTP/HTTPS probe server."""

from __future__ import annotations

import base64
import datetime
import hashlib
import http.server
import ipaddress
import socket
import ssl
import struct
import threading
import time
from pathlib import Path
from typing import Any

GREASE_VALUES = frozenset({
    0x0A0A, 0x1A1A, 0x2A2A, 0x3A3A, 0x4A4A, 0x5A5A, 0x6A6A, 0x7A7A,
    0x8A8A, 0x9A9A, 0xAAAA, 0xBABA, 0xCACA, 0xDADA, 0xEAEA, 0xFAFA,
})

ACCEPT_CH_HEADER = ", ".join([
    "Sec-CH-UA",
    "Sec-CH-UA-Mobile",
    "Sec-CH-UA-Platform",
    "Sec-CH-UA-Platform-Version",
    "Sec-CH-UA-Arch",
    "Sec-CH-UA-Bitness",
    "Sec-CH-UA-Model",
    "Sec-CH-UA-Full-Version-List",
])


def _alpn_tag(alpn_protocols: list[str]) -> str:
    if not alpn_protocols or not alpn_protocols[0]:
        return "00"
    first_alpn = alpn_protocols[0]
    if all(ch.isalnum() for ch in first_alpn) and len(first_alpn) >= 2:
        return first_alpn[0] + first_alpn[-1]
    if first_alpn == "http/1.1":
        return "h1"
    encoded = first_alpn.encode("ascii", "replace")
    return f"{encoded[0]:02x}"[0] + f"{encoded[-1]:02x}"[-1]


def parse_tls_client_hello(data: bytes) -> dict[str, Any] | None:
    """Parse a raw TLS ClientHello record and compute JA3, sorted-extension JA3, and JA4."""
    if len(data) < 5 or data[0] != 0x16:
        return None
    rec_ver = struct.unpack("!H", data[1:3])[0]
    rec_len = struct.unpack("!H", data[3:5])[0]
    if len(data) < 5 + rec_len:
        return None
    body = data[5 : 5 + rec_len]
    if len(body) < 4 or body[0] != 0x01:
        return None
    hs_len = int.from_bytes(body[1:4], "big")
    if len(body) < 4 + hs_len:
        return None
    hs = body[4 : 4 + hs_len]
    if len(hs) < 34:
        return None

    legacy_ver = struct.unpack("!H", hs[0:2])[0]
    offset = 2 + 32  # legacy_version + 32-byte random
    if offset >= len(hs):
        return None
    sid_len = hs[offset]
    offset += 1 + sid_len
    if offset + 2 > len(hs):
        return None
    cs_len = struct.unpack("!H", hs[offset : offset + 2])[0]
    offset += 2
    if cs_len % 2 != 0 or offset + cs_len > len(hs):
        return None
    ciphers_raw = [
        struct.unpack("!H", hs[offset + i : offset + i + 2])[0]
        for i in range(0, cs_len, 2)
    ]
    offset += cs_len
    if offset >= len(hs):
        return None
    comp_len = hs[offset]
    offset += 1 + comp_len
    if offset > len(hs):
        return None

    extensions_raw: list[int] = []
    sni_hosts: list[str] = []
    alpn_protocols: list[str] = []
    supported_groups: list[int] = []
    ec_point_formats: list[int] = []
    signature_algorithms: list[int] = []
    supported_versions: list[int] = []

    if offset + 2 <= len(hs):
        ext_total_len = struct.unpack("!H", hs[offset : offset + 2])[0]
        offset += 2
        if offset + ext_total_len > len(hs):
            return None
        ext_end = offset + ext_total_len
        while offset + 4 <= ext_end:
            etype, elen = struct.unpack("!HH", hs[offset : offset + 4])
            offset += 4
            if offset + elen > ext_end:
                return None
            edata = hs[offset : offset + elen]
            offset += elen
            extensions_raw.append(etype)
            if etype == 0x0000 and len(edata) >= 2:
                list_len = struct.unpack("!H", edata[0:2])[0]
                if 2 + list_len > len(edata):
                    return None
                pos = 2
                while pos + 3 <= 2 + list_len:
                    ntype = edata[pos]
                    nlen = struct.unpack("!H", edata[pos + 1 : pos + 3])[0]
                    pos += 3
                    if pos + nlen > 2 + list_len:
                        return None
                    if ntype == 0:
                        sni_hosts.append(
                            edata[pos : pos + nlen].decode("ascii", "replace")
                        )
                    pos += nlen
            elif etype == 0x000A and len(edata) >= 2:
                glen = struct.unpack("!H", edata[0:2])[0]
                if glen % 2 != 0 or 2 + glen > len(edata):
                    return None
                supported_groups = [
                    struct.unpack("!H", edata[2 + i : 2 + i + 2])[0]
                    for i in range(0, glen, 2)
                ]
            elif etype == 0x000B and len(edata) >= 1:
                plen = edata[0]
                if 1 + plen > len(edata):
                    return None
                ec_point_formats = list(edata[1 : 1 + plen])
            elif etype == 0x000D and len(edata) >= 2:
                slen = struct.unpack("!H", edata[0:2])[0]
                if slen % 2 != 0 or 2 + slen > len(edata):
                    return None
                signature_algorithms = [
                    struct.unpack("!H", edata[2 + i : 2 + i + 2])[0]
                    for i in range(0, slen, 2)
                ]
            elif etype == 0x0010 and len(edata) >= 2:
                alen = struct.unpack("!H", edata[0:2])[0]
                if 2 + alen > len(edata):
                    return None
                pos = 2
                while pos < 2 + alen:
                    plen = edata[pos]
                    pos += 1
                    if plen == 0 or pos + plen > 2 + alen:
                        return None
                    alpn_protocols.append(
                        edata[pos : pos + plen].decode("ascii", "replace")
                    )
                    pos += plen
            elif etype == 0x002B and len(edata) >= 1:
                vlen = edata[0]
                if vlen % 2 != 0 or 1 + vlen > len(edata):
                    return None
                supported_versions = [
                    struct.unpack("!H", edata[1 + i : 1 + i + 2])[0]
                    for i in range(0, vlen, 2)
                ]

    ciphers_nogrease = [c for c in ciphers_raw if c not in GREASE_VALUES]
    exts_nogrease = [e for e in extensions_raw if e not in GREASE_VALUES]
    groups_nogrease = [g for g in supported_groups if g not in GREASE_VALUES]
    sv_nogrease = [v for v in supported_versions if v not in GREASE_VALUES]

    ja3_raw = ",".join([
        str(legacy_ver),
        "-".join(str(c) for c in ciphers_nogrease),
        "-".join(str(e) for e in exts_nogrease),
        "-".join(str(g) for g in groups_nogrease),
        "-".join(str(p) for p in ec_point_formats),
    ])
    ja3 = hashlib.md5(ja3_raw.encode("ascii")).hexdigest()

    ja3_sorted_raw = ",".join([
        str(legacy_ver),
        "-".join(str(c) for c in ciphers_nogrease),
        "-".join(str(e) for e in sorted(exts_nogrease)),
        "-".join(str(g) for g in groups_nogrease),
        "-".join(str(p) for p in ec_point_formats),
    ])
    ja3_sorted = hashlib.md5(ja3_sorted_raw.encode("ascii")).hexdigest()

    max_ver = max(sv_nogrease) if sv_nogrease else legacy_ver
    ver_map = {0x0304: "13", 0x0303: "12", 0x0302: "11", 0x0301: "10"}
    ja4_ver = ver_map.get(max_ver, "00")
    sni_char = "d" if sni_hosts else "i"
    cipher_count = f"{min(len(ciphers_nogrease), 99):02d}"
    ext_count = f"{min(len(exts_nogrease), 99):02d}"
    ja4_a = f"t{ja4_ver}{sni_char}{cipher_count}{ext_count}{_alpn_tag(alpn_protocols)}"

    sorted_ciphers = ",".join(f"{c:04x}" for c in sorted(ciphers_nogrease))
    ja4_b = hashlib.sha256(sorted_ciphers.encode("ascii")).hexdigest()[:12]
    exts_for_c = sorted(e for e in exts_nogrease if e not in (0x0000, 0x0010))
    c_ext_part = ",".join(f"{e:04x}" for e in exts_for_c)
    c_sig_part = ",".join(f"{s:04x}" for s in signature_algorithms)
    ja4_c_input = f"{c_ext_part}_{c_sig_part}" if c_sig_part else c_ext_part
    ja4_c = hashlib.sha256(ja4_c_input.encode("ascii")).hexdigest()[:12]
    ja4 = f"{ja4_a}_{ja4_b}_{ja4_c}"

    return {
        "record_version": f"0x{rec_ver:04x}",
        "legacy_version": f"0x{legacy_ver:04x}",
        "supported_versions": [f"0x{v:04x}" for v in sv_nogrease],
        "cipher_count_raw": len(ciphers_raw),
        "cipher_count": len(ciphers_nogrease),
        "ciphers": [f"0x{c:04x}" for c in ciphers_nogrease],
        "extension_count_raw": len(extensions_raw),
        "extension_count": len(exts_nogrease),
        "extensions_order": [f"0x{e:04x}" for e in exts_nogrease],
        "extensions_set": sorted(f"0x{e:04x}" for e in exts_nogrease),
        "grease_count_ciphers": len(ciphers_raw) - len(ciphers_nogrease),
        "grease_count_extensions": len(extensions_raw) - len(exts_nogrease),
        "supported_groups": [f"0x{g:04x}" for g in groups_nogrease],
        "ec_point_formats": ec_point_formats,
        "signature_algorithms": [f"0x{s:04x}" for s in signature_algorithms],
        "alpn": alpn_protocols,
        "sni": sni_hosts,
        "ja3": ja3,
        "ja3_raw": ja3_raw,
        "ja3_sorted": ja3_sorted,
        "ja4": ja4,
        "ja4_a": ja4_a,
    }


def make_ephemeral_cert(tmpdir: Path) -> tuple[Path, Path, str]:
    """Generate an ephemeral RSA-2048 cert for localhost / 127.0.0.1 and return (cert, key, spki_sha256_b64)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path = tmpdir / "probe_cert.pem"
    key_path = tmpdir / "probe_key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    spki_der = key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    spki_hash = base64.b64encode(hashlib.sha256(spki_der).digest()).decode("ascii")
    return cert_path, key_path, spki_hash


COLLECTOR_JS = r"""
async function collectContext(ctxName) {
  const out = { context: ctxName, status: "ok", metrics: {} };
  const unsupported = (reason) => ({ status: "unsupported_context", reason });
  const wrap = async (fn) => {
    try { return { status: "ok", value: await fn() }; }
    catch (e) { return { status: "error", error: String(e) }; }
  };

  const nav = self.navigator;
  out.metrics.userAgent = { status: "ok", value: nav.userAgent };
  out.metrics.platform = { status: "ok", value: nav.platform };
  out.metrics.language = { status: "ok", value: nav.language };
  out.metrics.languages = { status: "ok", value: Array.from(nav.languages || []) };
  out.metrics.hardwareConcurrency = { status: "ok", value: nav.hardwareConcurrency };
  out.metrics.deviceMemory = nav.deviceMemory === undefined
    ? { status: "unsupported_api", reason: "navigator.deviceMemory undefined" }
    : { status: "ok", value: nav.deviceMemory };
  out.metrics.webdriver = nav.webdriver === undefined
    ? unsupported("navigator.webdriver unavailable in worker")
    : { status: "ok", value: nav.webdriver };
  out.metrics.pdfViewerEnabled = nav.pdfViewerEnabled === undefined
    ? unsupported("navigator.pdfViewerEnabled unavailable in worker")
    : { status: "ok", value: nav.pdfViewerEnabled };

  if (nav.userAgentData) {
    out.metrics.uaDataLow = {
      status: "ok",
      value: {
        brands: nav.userAgentData.brands,
        mobile: nav.userAgentData.mobile,
        platform: nav.userAgentData.platform,
      },
    };
    out.metrics.uaDataHigh = await wrap(() => nav.userAgentData.getHighEntropyValues([
      "architecture", "bitness", "brands", "fullVersionList",
      "mobile", "model", "platform", "platformVersion", "uaFullVersion", "wow64"
    ]));
  } else {
    out.metrics.uaDataLow = unsupported("navigator.userAgentData absent");
    out.metrics.uaDataHigh = unsupported("navigator.userAgentData absent");
  }

  out.metrics.timezone = { status: "ok", value: Intl.DateTimeFormat().resolvedOptions().timeZone };

  if (typeof window !== "undefined" && typeof screen !== "undefined") {
    out.metrics.screen = {
      status: "ok",
      value: {
        width: screen.width, height: screen.height,
        availWidth: screen.availWidth, availHeight: screen.availHeight,
        colorDepth: screen.colorDepth, pixelDepth: screen.pixelDepth,
        devicePixelRatio: window.devicePixelRatio,
        innerWidth: window.innerWidth, innerHeight: window.innerHeight,
        outerWidth: window.outerWidth, outerHeight: window.outerHeight,
      },
    };
  } else {
    out.metrics.screen = unsupported("window/screen undefined in worker");
  }

  if (nav.storage && nav.storage.estimate) {
    out.metrics.storageEstimate = await wrap(() => nav.storage.estimate());
  } else {
    out.metrics.storageEstimate = unsupported("navigator.storage.estimate unavailable");
  }

  out.metrics.canvas2d = await wrap(async () => {
    let canvas, ctx;
    if (typeof document !== "undefined") {
      canvas = document.createElement("canvas");
      canvas.width = 240; canvas.height = 50;
      ctx = canvas.getContext("2d");
      ctx.textBaseline = "top";
      ctx.font = '14px "Arial", "Microsoft YaHei", "PingFang SC", sans-serif';
      ctx.fillStyle = "#f60"; ctx.fillRect(10, 5, 62, 20);
      ctx.fillStyle = "#069"; ctx.fillText("CBrowser-FP-probe-中文", 2, 15);
      const dataUrl = canvas.toDataURL();
      let h = 0x811c9dc5;
      for (let i = 0; i < dataUrl.length; i++) {
        h ^= dataUrl.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0;
      }
      return ("00000000" + h.toString(16)).slice(-8);
    } else if (typeof OffscreenCanvas !== "undefined") {
      canvas = new OffscreenCanvas(240, 50);
      ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("OffscreenCanvas 2d null");
      ctx.textBaseline = "top";
      ctx.font = '14px "Arial", "Microsoft YaHei", "PingFang SC", sans-serif';
      ctx.fillStyle = "#f60"; ctx.fillRect(10, 5, 62, 20);
      ctx.fillStyle = "#069"; ctx.fillText("CBrowser-FP-probe-中文", 2, 15);
      const img = ctx.getImageData(0, 0, 240, 50).data;
      let h = 0x811c9dc5;
      for (let i = 0; i < img.length; i++) {
        h ^= img[i]; h = Math.imul(h, 0x01000193) >>> 0;
      }
      return "offscreen:" + ("00000000" + h.toString(16)).slice(-8);
    }
    throw new Error("no canvas api");
  });

  out.metrics.webgl = await wrap(async () => {
    let gl = null;
    if (typeof document !== "undefined") {
      gl = document.createElement("canvas").getContext("webgl");
    } else if (typeof OffscreenCanvas !== "undefined") {
      gl = new OffscreenCanvas(64, 64).getContext("webgl");
    }
    if (!gl) return { available: false };
    const ext = gl.getExtension("WEBGL_debug_renderer_info");
    return {
      available: true,
      vendor: gl.getParameter(gl.VENDOR),
      renderer: gl.getParameter(gl.RENDERER),
      unmaskedVendor: ext ? gl.getParameter(ext.UNMASKED_VENDOR_WEBGL) : null,
      unmaskedRenderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null,
      version: gl.getParameter(gl.VERSION),
      maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE),
    };
  });

  if (typeof OfflineAudioContext !== "undefined") {
    out.metrics.audio = await wrap(async () => {
      const ctx = new OfflineAudioContext(1, 5000, 44100);
      const osc = ctx.createOscillator();
      osc.type = "triangle"; osc.frequency.value = 10000;
      const comp = ctx.createDynamicsCompressor();
      comp.threshold.value = -50; comp.knee.value = 40; comp.ratio.value = 12;
      comp.attack.value = 0; comp.release.value = 0.25;
      osc.connect(comp); comp.connect(ctx.destination);
      osc.start(0);
      const buf = await ctx.startRendering();
      const ch = buf.getChannelData(0);
      let sum = 0;
      for (let i = 4500; i < 5000; i++) sum += Math.abs(ch[i]);
      return Math.round(sum * 1e6) / 1e6;
    });
  } else {
    out.metrics.audio = unsupported("OfflineAudioContext unavailable in worker");
  }

  out.metrics.fonts = await wrap(async () => {
    const families = [
      "Segoe UI", "Calibri", "Consolas", "Microsoft YaHei", "SimSun",
      "PingFang SC", "Hiragino Sans GB", "Helvetica Neue", "Menlo",
      "Liberation Sans", "WenQuanYi Zen Hei", "DejaVu Sans"
    ];
    let ctx;
    if (typeof document !== "undefined") {
      ctx = document.createElement("canvas").getContext("2d");
    } else if (typeof OffscreenCanvas !== "undefined") {
      ctx = new OffscreenCanvas(300, 50).getContext("2d");
    }
    if (!ctx) throw new Error("no 2d ctx");
    const sample = "mmlliWW中文😀";
    const baseMeasure = {};
    for (const base of ["monospace", "sans-serif", "serif"]) {
      ctx.font = `40px ${base}`;
      baseMeasure[base] = ctx.measureText(sample).width;
    }
    const widths = {};
    for (const fam of families) {
      ctx.font = `40px "${fam}", monospace`;
      widths[fam] = ctx.measureText(sample).width;
    }
    return { base: baseMeasure, widths };
  });

  if (typeof RTCPeerConnection !== "undefined") {
    out.metrics.webrtc = await wrap(async () => {
      const pc = new RTCPeerConnection({ iceServers: [] });
      pc.createDataChannel("fp");
      const cands = [];
      pc.onicecandidate = (e) => {
        if (e.candidate && e.candidate.candidate) cands.push(e.candidate.candidate);
      };
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      await new Promise((res) => {
        if (pc.iceGatheringState === "complete") return res();
        const t = setTimeout(res, 1200);
        pc.onicegatheringstatechange = () => {
          if (pc.iceGatheringState === "complete") { clearTimeout(t); res(); }
        };
      });
      pc.close();
      return cands.map((raw) => {
        const parts = raw.split(" ");
        return {
          protocol: parts[2] || null,
          address: parts[4] || null,
          type: parts[7] || null,
        };
      });
    });
  } else {
    out.metrics.webrtc = unsupported("RTCPeerConnection unavailable in worker");
  }

  return out;
}
"""

MAIN_HTML = (
    "<!doctype html><title>cbrowser-fp-probe</title><body>"
    "<iframe id='fp-frame' src='/iframe'></iframe>"
    "<script>\n"
    + COLLECTOR_JS
    + r"""
const __fpTimeout = (p, ms, tag) => Promise.race([
  p,
  new Promise((res) => setTimeout(() => res({ __fp_timeout: tag }), ms))
]);
const __fpIsTimeout = (v) => v && typeof v === "object" && "__fp_timeout" in v;
// Register before the iframe subdocument can postMessage: the listener is
// installed synchronously as the parent script runs, ahead of the child's
// async collectContext() round-trip.
window.__fpIframePromise = new Promise((resolve) => {
  window.addEventListener("message", (e) => {
    if (e.data && e.data.context === "iframe") resolve(e.data);
  });
});
window.__fpProbeDone = (async () => {
  console.log("FP:start");
  const main = await collectContext("main");
  console.log("FP:main");
  await fetch("/main-fetch");
  const iframePromise = window.__fpIframePromise;
  const workerPromise = new Promise((resolve) => {
    const w = new Worker("/worker.js");
    w.onmessage = (e) => resolve(e.data);
    w.onerror = (e) => resolve({ context: "worker", status: "error", error: String(e.message) });
  });
  let workerRes = await __fpTimeout(workerPromise, 10000, "worker");
  if (__fpIsTimeout(workerRes)) {
    workerRes = { context: "worker", status: "error", error: "worker_timeout" };
  }
  console.log("FP:worker");
  let swRes;
  try {
    const reg = await __fpTimeout(navigator.serviceWorker.register("/sw.js"), 8000, "sw_register");
    console.log("FP:swreg");
    if (__fpIsTimeout(reg)) throw new Error("service_worker_register_timeout");
    const ready = await __fpTimeout(navigator.serviceWorker.ready, 8000, "sw_ready");
    console.log("FP:swready");
    if (__fpIsTimeout(ready)) throw new Error("service_worker_ready_timeout");
    if (!navigator.serviceWorker.controller) {
      await new Promise((res) => {
        navigator.serviceWorker.addEventListener("controllerchange", res, { once: true });
        setTimeout(res, 1500);
      });
    }
    swRes = await __fpTimeout(fetch("/sw-probe").then((r) => r.json()), 10000, "sw_fetch");
    console.log("FP:swres");
    if (__fpIsTimeout(swRes)) throw new Error("service_worker_fetch_timeout");
  } catch (e) {
    swRes = { context: "service_worker", status: "error", error: String(e) };
  }
  let iframeRes = await __fpTimeout(iframePromise, 8000, "iframe");
  if (__fpIsTimeout(iframeRes)) {
    iframeRes = { context: "iframe", status: "error", error: "iframe_timeout" };
  }
  console.log("FP:iframe");
  return { main, iframe: iframeRes, worker: workerRes, service_worker: swRes };
})();
</script></body>"""
)

IFRAME_HTML = (
    "<!doctype html><title>fp-iframe</title><script>\n"
    + COLLECTOR_JS
    + r"""
(async () => {
  let data;
  try { data = await collectContext('iframe'); }
  catch (e) { data = { context: 'iframe', status: 'error', error: String(e), metrics: {} }; }
  // Idempotent redelivery: the parent listener resolves once and ignores later
  // messages, so a child script running before the parent's listener is safe.
  parent.postMessage(data, '*');
  setTimeout(() => parent.postMessage(data, '*'), 100);
  setTimeout(() => parent.postMessage(data, '*'), 500);
})();
</script>"""
)

WORKER_JS = (
    COLLECTOR_JS
    + "\n(async () => { await fetch('/worker-fetch'); self.postMessage(await collectContext('worker')); })();\n"
)

SW_JS = (
    COLLECTOR_JS
    + r"""
self.addEventListener('install', (e) => e.waitUntil(self.skipWaiting()));
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', (e) => {
  if (e.request.url.includes('/sw-probe')) {
    e.respondWith((async () => {
      const data = await collectContext('service_worker');
      await fetch('/sw-fetch');
      return new Response(JSON.stringify(data), {
        headers: { 'Content-Type': 'application/json' }
      });
    })());
  }
});
"""
)


class _ProbeHTTPServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_cls: type[http.server.BaseHTTPRequestHandler],
        ssl_ctx: ssl.SSLContext | None,
        tls_records: list[dict[str, Any]],
    ) -> None:
        self.ssl_ctx = ssl_ctx
        self.tls_records = tls_records
        super().__init__(server_address, handler_cls)

    def get_request(self):
        sock, addr = self.socket.accept()
        sock.settimeout(5.0)
        if self.ssl_ctx is None:
            return sock, addr
        peeked = b""
        for _ in range(20):
            try:
                peeked = sock.recv(16384, socket.MSG_PEEK)
                if len(peeked) >= 5:
                    rec_len = struct.unpack("!H", peeked[3:5])[0]
                    if len(peeked) >= 5 + rec_len:
                        break
            except OSError:
                break
            time.sleep(0.01)
        parsed = parse_tls_client_hello(peeked) if peeked else None
        wrapped = self.ssl_ctx.wrap_socket(sock, server_side=True)
        tls_info = {
            "cipher": list(wrapped.cipher()) if wrapped.cipher() else None,
            "tls_version": wrapped.version(),
            "alpn_selected": wrapped.selected_alpn_protocol(),
            "client_hello": parsed,
        }
        self.tls_records.append(tls_info)
        wrapped._cb_tls_info = tls_info  # type: ignore[attr-defined]
        return wrapped, addr


class TLSObservingProbeServer:
    """Self-hosted local HTTPS/HTTP server observing TLS ClientHello & HTTP headers."""

    def __init__(self, *, use_tls: bool = True, host: str | None = None) -> None:
        self.use_tls = use_tls
        self.host = host or ("localhost" if use_tls else "127.0.0.1")
        self.tls_records: list[dict[str, Any]] = []
        self.http_records: list[dict[str, Any]] = []
        self._tmpdir: Path | None = None
        self.spki_hash: str | None = None
        self._server: _ProbeHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "TLSObservingProbeServer":
        import tempfile

        ssl_ctx: ssl.SSLContext | None = None
        if self.use_tls:
            self._tmpdir = Path(tempfile.mkdtemp(prefix="cb-fp-tls-"))
            cert_path, key_path, self.spki_hash = make_ephemeral_cert(self._tmpdir)
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
            ssl_ctx.set_alpn_protocols(["http/1.1"])

        tls_records = self.tls_records
        http_records = self.http_records

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                tls_info = getattr(self.connection, "_cb_tls_info", None)
                headers_norm = {
                    k.lower(): v
                    for k, v in self.headers.items()
                    if k.lower().startswith("sec-ch-ua")
                    or k.lower() in ("user-agent", "accept-language")
                }
                http_records.append({
                    "path": self.path,
                    "headers": headers_norm,
                    "tls_ja4": (
                        tls_info["client_hello"]["ja4"]
                        if tls_info and tls_info.get("client_hello")
                        else None
                    ),
                    "tls_ja3": (
                        tls_info["client_hello"]["ja3"]
                        if tls_info and tls_info.get("client_hello")
                        else None
                    ),
                })
                routes = {
                    "/": (MAIN_HTML.encode("utf-8"), "text/html; charset=utf-8"),
                    "/iframe": (IFRAME_HTML.encode("utf-8"), "text/html; charset=utf-8"),
                    "/worker.js": (WORKER_JS.encode("utf-8"), "application/javascript"),
                    "/sw.js": (SW_JS.encode("utf-8"), "application/javascript"),
                    "/main-fetch": (b"ok", "text/plain"),
                    "/worker-fetch": (b"ok", "text/plain"),
                    "/sw-fetch": (b"ok", "text/plain"),
                }
                body, ctype = routes.get(self.path, (b"ok", "text/plain"))
                code = 200 if self.path in routes or self.path == "/favicon.ico" else 404
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Accept-CH", ACCEPT_CH_HEADER)
                self.send_header("Critical-CH", ACCEPT_CH_HEADER)
                self.send_header("Service-Worker-Allowed", "/")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                return

        self._server = _ProbeHTTPServer(("127.0.0.1", 0), Handler, ssl_ctx, tls_records)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._tmpdir is not None:
            import shutil

            shutil.rmtree(self._tmpdir, ignore_errors=True)

    @property
    def port(self) -> int:
        assert self._server is not None
        return int(self._server.server_address[1])

    @property
    def origin(self) -> str:
        scheme = "https" if self.use_tls else "http"
        return f"{scheme}://{self.host}:{self.port}/"

    def reset_records(self) -> None:
        self.tls_records.clear()
        self.http_records.clear()
