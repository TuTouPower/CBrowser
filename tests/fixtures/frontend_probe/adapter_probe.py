"""Test-only probe injected into Selkies assets for frontend E2E evidence."""

from __future__ import annotations

from pathlib import Path

PROBE_TAG = '<script src="./adapter_probe.js"></script>'

PROBE_JS = r"""(() => {
    if (window.__cbrowserTestProbeInstalled) return;
    window.__cbrowserTestProbeInstalled = true;

    const NativeWebSocket = window.WebSocket;
    window.WebSocket = function(...args) {
        const ws = new NativeWebSocket(...args);
        window.__last_ws = ws;
        return ws;
    };
    window.WebSocket.prototype = NativeWebSocket.prototype;
    Object.assign(window.WebSocket, NativeWebSocket);

    const NativeRTCPeerConnection = window.RTCPeerConnection;
    window.RTCPeerConnection = function(...args) {
        const pc = new NativeRTCPeerConnection(...args);
        window.__activePC = pc;
        window.__pcs = window.__pcs || [];
        window.__pcs.push(pc);
        if (typeof pc.addEventListener === 'function') {
            pc.addEventListener('datachannel', event => {
                if (event.channel && event.channel.label === 'input') {
                    window.__inputChannel = event.channel;
                }
            });
        }
        return pc;
    };
    window.RTCPeerConnection.prototype = NativeRTCPeerConnection.prototype;
    Object.assign(window.RTCPeerConnection, NativeRTCPeerConnection);

    const NativeSend = window.RTCDataChannel.prototype.send;
    window.__sentDataChannelMessages = [];
    // Per-type counters that survive buffer eviction (t024 AC-018/A53):
    // control-class assertions must not depend on a message still being
    // inside the 500-entry rolling buffer.
    window.__sentDataChannelCounts = {};
    window.__droppedDataChannelMessages = 0;
    window.RTCDataChannel.prototype.send = function(data) {
        if (typeof data === 'string') {
            let key = 'text';
            try {
                const parsed = JSON.parse(data);
                key = parsed.type || parsed.kind || 'json';
            } catch (e) {
                key = (data.split(/[\s,]/)[0] || 'text').slice(0, 32);
            }
            window.__sentDataChannelCounts[key] =
                (window.__sentDataChannelCounts[key] || 0) + 1;
            window.__sentDataChannelMessages.push(data);
            if (window.__sentDataChannelMessages.length > 500) {
                window.__sentDataChannelMessages.shift();
                window.__droppedDataChannelMessages += 1;
            }
        }
        return NativeSend.call(this, data);
    };
})();
"""


def inject_adapter_probe(selkies_index: Path) -> None:
    """Inject the recording probe into the copied Selkies index before its module."""
    index = selkies_index
    html = index.read_text(encoding="utf-8")
    if PROBE_TAG in html:
        return
    (index.parent / "adapter_probe.js").write_text(PROBE_JS, encoding="utf-8")
    adapter_tag = '<script src="./selkies_adapter.js"></script>'
    if adapter_tag not in html:
        raise RuntimeError("Selkies adapter tag missing from copied index")
    html = html.replace(adapter_tag, PROBE_TAG + "\n" + adapter_tag, 1)
    index.write_text(html, encoding="utf-8")
