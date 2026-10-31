"""Prepare Selkies 2.1.0 official web client assets with gateway adapter."""

from __future__ import annotations

import hashlib
import io
import shutil
import tarfile
from pathlib import Path

import docker

# SHA-256 of every Selkies 2.1.0 web asset (selkies_web/, bytecode excluded),
# taken from the pinned wheel installed in the Stream image.
REF_MANIFEST = Path(__file__).with_name("selkies_web_sha256.txt")

CLIENT_SHIM_SCRIPT = r"""<script>
(() => {
    if (window.__cbrowserShimInstalled) return;
    window.__cbrowserShimInstalled = true;
    window.__cbrowserIdentityGuard = true;
    window.__SELKIES_STREAMING_MODE__ = 'webrtc';

    const NativeWebSocket = window.WebSocket;
    const NativeRTCPeerConnection = window.RTCPeerConnection;
    const NativeSetConfiguration = NativeRTCPeerConnection.prototype.setConfiguration;
    const NativeDataChannelSend = RTCDataChannel.prototype.send;
    window.__NativeWebSocket = NativeWebSocket;
    window.__NativeRTCPeerConnection = NativeRTCPeerConnection;
    window.__sentDataChannelMessages = [];

    RTCDataChannel.prototype.send = function(data) {
        window.__sentDataChannelMessages.push(data);
        return NativeDataChannelSend.call(this, data);
    };

    let activePC = null;
    let latestRtcConfig = null;
    let activeWS = null;

    let heldId = null;
    const acquisitions = new Map();

    function acquire(id) {
        if (heldId === id) return Promise.resolve(true);
        if (acquisitions.has(id)) return acquisitions.get(id);
        const pending = new Promise((resolve, reject) => {
            if (!navigator.locks) {
                reject(new Error('Web Locks required'));
                return;
            }
            navigator.locks.request('cbrowser_tab_lock_' + id,
                {ifAvailable: true}, lock => {
                    if (!lock) {
                        resolve(false);
                        return;
                    }
                    heldId = id;
                    resolve(true);
                    return new Promise(() => {});
                }).catch(reject);
        });
        acquisitions.set(id, pending);
        pending.finally(() => acquisitions.delete(id)).catch(() => {});
        return pending;
    }

    // RTCPeerConnection wrapper
    window.RTCPeerConnection = function(...args) {
        let config = args[0] ? Object.assign({}, args[0]) : {};
        if (latestRtcConfig) {
            if (latestRtcConfig.iceServers) {
                config.iceServers = latestRtcConfig.iceServers;
            }
            if (latestRtcConfig.iceTransportPolicy) {
                config.iceTransportPolicy = latestRtcConfig.iceTransportPolicy;
            }
        }
        const params = new URLSearchParams(location.search);
        if (params.get('webrtc_mode') === 'relay-only'
            || window.__CBROWSER_WEBRTC_MODE__ === 'relay-only'
            || (latestRtcConfig && latestRtcConfig.iceTransportPolicy === 'relay')) {
            config.iceTransportPolicy = 'relay';
        }
        const pc = new NativeRTCPeerConnection(config);
        activePC = pc;
        window.__activePC = pc;
        window.__pcs = window.__pcs || [];
        window.__pcs.push(pc);

        pc.addEventListener('datachannel', event => {
            if (event.channel.label === 'input') {
                window.__inputChannel = event.channel;
            }
        });
        return pc;
    };
    window.RTCPeerConnection.prototype = NativeRTCPeerConnection.prototype;
    Object.assign(window.RTCPeerConnection, NativeRTCPeerConnection);

    RTCPeerConnection.prototype.setConfiguration = function(config) {
        let merged = config ? Object.assign({}, config) : {};
        if (latestRtcConfig) {
            if (latestRtcConfig.iceServers) {
                merged.iceServers = latestRtcConfig.iceServers;
            }
            if (latestRtcConfig.iceTransportPolicy) {
                merged.iceTransportPolicy = latestRtcConfig.iceTransportPolicy;
            }
        }
        const params = new URLSearchParams(location.search);
        if (params.get('webrtc_mode') === 'relay-only'
            || window.__CBROWSER_WEBRTC_MODE__ === 'relay-only'
            || (latestRtcConfig && latestRtcConfig.iceTransportPolicy === 'relay')) {
            merged.iceTransportPolicy = 'relay';
        }
        return NativeSetConfiguration.call(this, merged);
    };

    // WebSocket wrapper
    window.WebSocket = function(url, protocols) {
        const u = new URL(url, location.href);
        const params = new URLSearchParams(location.search);
        const profileId = params.get('profile_id')
            || window.__CBROWSER_PROFILE_ID__ || 'default';
        if (u.pathname.includes('/signaling')
            || u.pathname.endsWith('/api/ws')
            || u.pathname.includes('/stream/')) {
            u.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            u.host = location.host;
            u.pathname = `/stream/${profileId}/signal`;
        }

        const ws = protocols !== undefined
            ? new NativeWebSocket(u.toString(), protocols)
            : new NativeWebSocket(u.toString());
        activeWS = ws;
        window.__last_ws = ws;

        const nativeSend = ws.send.bind(ws);

        ws.send = function(data) {
            if (typeof data === 'string' && data.startsWith('HELLO client ')) {
                let id = sessionStorage.getItem('selkies_tab_id');
                if (!id) {
                    id = crypto.randomUUID();
                    sessionStorage.setItem('selkies_tab_id', id);
                }
                acquire(id).then(acquired => {
                    if (ws.readyState !== NativeWebSocket.OPEN) return;
                    if (!acquired) {
                        sessionStorage.setItem('selkies_tab_id', crypto.randomUUID());
                        ws.close(1000, 'tab_collision_remap');
                        return;
                    }
                    nativeSend(data);
                }).catch(() => ws.close(1008, 'tab_identity_unavailable'));
                return;
            }
            if (typeof data === 'string'
                && data.includes('"cbrowser"')
                && data.includes('"activity"')) {
                return;
            }
            nativeSend(data);
        };

        let userOnMessage = null;
        Object.defineProperty(ws, 'onmessage', {
            get() {
                return userOnMessage;
            },
            set(handler) {
                userOnMessage = handler;
            },
            configurable: true,
        });

        const origAddEventListener = ws.addEventListener.bind(ws);
        const origRemoveEventListener = ws.removeEventListener.bind(ws);
        const wrappedListeners = new Map();

        ws.addEventListener = function(type, listener, options) {
            if (type === 'message' && typeof listener === 'function') {
                const wrapped = function(event) {
                    const data = event.data;
                    if (typeof data === 'string' && data.includes('"cbrowser"')) {
                        try {
                            const parsed = JSON.parse(data);
                            if (parsed && parsed.cbrowser) {
                                return;
                            }
                        } catch (e) {}
                    }
                    return listener.call(this, event);
                };
                wrappedListeners.set(listener, wrapped);
                return origAddEventListener(type, wrapped, options);
            }
            return origAddEventListener(type, listener, options);
        };

        ws.removeEventListener = function(type, listener, options) {
            if (type === 'message' && wrappedListeners.has(listener)) {
                const wrapped = wrappedListeners.get(listener);
                wrappedListeners.delete(listener);
                return origRemoveEventListener(type, wrapped, options);
            }
            return origRemoveEventListener(type, listener, options);
        };

        origAddEventListener('message', async (event) => {
            const data = event.data;
            if (typeof data === 'string' && data.includes('"cbrowser"')) {
                try {
                    const parsed = JSON.parse(data);
                    if (parsed && parsed.cbrowser) {
                        if (parsed.cbrowser === 'rtc_config') {
                            latestRtcConfig = parsed.rtc_config;
                            window.__latestRtcConfig = parsed.rtc_config;
                            if (activePC) {
                                try {
                                    activePC.setConfiguration(parsed.rtc_config);
                                } catch (e) {}
                            }
                        } else if (parsed.cbrowser === 'ice_restart') {
                            window.__restartOffers = window.__restartOffers || [];
                            let offerUfrag = null;
                            if (parsed.offer && parsed.offer.sdp) {
                                for (const line of parsed.offer.sdp.split('\n')) {
                                    const trim = line.trim();
                                    if (trim.startsWith('a=ice-ufrag:')) {
                                        offerUfrag = trim.split(':', 2)[1].trim();
                                        break;
                                    }
                                }
                            }
                            window.__restartOffers.push({
                                generation: parsed.generation,
                                ufrag: offerUfrag,
                                offer: parsed.offer,
                            });

                            if (window.__negativeRejectClientTurn
                                || location.search.includes('negative_turn_reject=1')) {
                                if (parsed.rtc_config && parsed.rtc_config.iceServers) {
                                    for (const s of parsed.rtc_config.iceServers) {
                                        s.credential =
                                            "invalid-password-for-negative-test";
                                    }
                                }
                            }
                            if (parsed.rtc_config) {
                                latestRtcConfig = parsed.rtc_config;
                                window.__latestRtcConfig = parsed.rtc_config;
                            }

                            if (activePC) {
                                try {
                                    if (parsed.rtc_config) {
                                        activePC.setConfiguration(parsed.rtc_config);
                                    }
                                    await activePC.setRemoteDescription(parsed.offer);
                                    const answer = await activePC.createAnswer();
                                    await activePC.setLocalDescription(answer);
                                    if (activePC.iceGatheringState !== 'complete') {
                                        await new Promise(resolve => {
                                            const check = () => {
                                                if (activePC.iceGatheringState
                                                    === 'complete') {
                                                    activePC.removeEventListener(
                                                        'icegatheringstatechange',
                                                        check
                                                    );
                                                    resolve();
                                                }
                                            };
                                            activePC.addEventListener(
                                                'icegatheringstatechange',
                                                check
                                            );
                                            setTimeout(resolve, 3000);
                                        });
                                    }
                                    const answerPayload = {
                                        cbrowser: "ice_restart_answer",
                                        generation: parsed.generation,
                                        sdp: {
                                            type: activePC.localDescription.type,
                                            sdp: activePC.localDescription.sdp,
                                        }
                                    };
                                    nativeSend(JSON.stringify(answerPayload));
                                } catch (err) {
                                    console.error("ice_restart failure:", err);
                                }
                            }
                        }
                        return;
                    }
                } catch (e) {}
            }
            if (userOnMessage) {
                userOnMessage.call(ws, event);
            }
        });

        return ws;
    };
    window.WebSocket.prototype = NativeWebSocket.prototype;
    Object.assign(window.WebSocket, NativeWebSocket);

    window.__getWebRTCStats = async () => {
        const pc = window.__activePC;
        if (!pc) return null;
        const report = await pc.getStats();
        let video = null;
        let audio = null;
        let pair = null;
        for (const stat of report.values()) {
            if (stat.type === 'inbound-rtp') {
                if (stat.kind === 'video') {
                    video = {
                        framesDecoded: stat.framesDecoded || 0,
                        keyFramesDecoded: stat.keyFramesDecoded || 0,
                        bytesReceived: stat.bytesReceived || 0,
                    };
                } else if (stat.kind === 'audio') {
                    audio = {
                        totalAudioEnergy: stat.totalAudioEnergy || 0,
                        bytesReceived: stat.bytesReceived || 0,
                    };
                }
            } else if (stat.type === 'transport' && stat.selectedCandidatePairId) {
                const p = report.get(stat.selectedCandidatePairId);
                if (p) {
                    const local = report.get(p.localCandidateId);
                    const remote = report.get(p.remoteCandidateId);
                    pair = {
                        localType: local ? local.candidateType : null,
                        remoteType: remote ? remote.candidateType : null,
                        remoteAddress: remote ? (remote.ip || remote.address) : null,
                        remotePort: remote ? remote.port : null,
                        remoteUfrag: remote ? remote.usernameFragment : null,
                        bytesReceived: p.bytesReceived || 0,
                    };
                }
            }
        }
        return {
            video,
            audio,
            pair,
            tab_id: sessionStorage.getItem('selkies_tab_id'),
            connected: pc.connectionState === 'connected'
                || pc.iceConnectionState === 'connected',
        };
    };
})();
</script>
"""


def verify_manifest(extracted_dir: Path, manifest_path: Path = REF_MANIFEST) -> None:
    """Verifies that extracted official files match reference sha256 manifest."""
    assert manifest_path.is_file(), f"Reference manifest not found at {manifest_path}"
    manifest_lines = manifest_path.read_text(encoding="utf-8").splitlines()
    for line in manifest_lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        expected_hash, rel_path = line.split(None, 1)
        clean_rel = rel_path.removeprefix("selkies_web/").strip()
        file_path = extracted_dir / clean_rel
        assert file_path.is_file(), f"Official Selkies asset missing: {clean_rel}"
        content = file_path.read_bytes()
        actual_hash = hashlib.sha256(content).hexdigest()
        assert actual_hash == expected_hash, (
            f"SHA256 mismatch for {clean_rel}: {expected_hash} != {actual_hash}"
        )


def prepare_selkies_web_assets(stream_image_id: str, dest_dir: Path) -> Path:
    """Extracts Selkies web client from Stream image and applies minimal adapter."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    index_file = dest_dir / "index.html"

    client = docker.from_env()
    container = client.containers.create(stream_image_id, entrypoint=["/bin/sh"])
    try:
        archive_stream, _ = container.get_archive(
            "/usr/local/lib/python3.12/site-packages/selkies/selkies_web"
        )
        archive_bytes = b"".join(archive_stream)
        with tarfile.open(fileobj=io.BytesIO(archive_bytes)) as tar:
            tar.extractall(path=dest_dir)
    finally:
        container.remove(force=True)

    extracted_root = dest_dir / "selkies_web"
    if extracted_root.is_dir():
        for item in extracted_root.iterdir():
            target = dest_dir / item.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.move(str(item), str(dest_dir))
        extracted_root.rmdir()

    # Verify SHA256 of extracted assets against reference manifest
    verify_manifest(dest_dir)

    # Inject client shim into index.html
    raw_html = index_file.read_text(encoding="utf-8")
    marker = (
        '<script type="module" crossorigin src="./assets/index-BpOBp7NB.js"></script>'
    )
    if marker in raw_html:
        adapted_html = raw_html.replace(marker, CLIENT_SHIM_SCRIPT + "\n" + marker, 1)
    elif "<head>" in raw_html:
        adapted_html = raw_html.replace("<head>", "<head>\n" + CLIENT_SHIM_SCRIPT, 1)
    else:
        adapted_html = CLIENT_SHIM_SCRIPT + "\n" + raw_html
    index_file.write_text(adapted_html, encoding="utf-8")

    return dest_dir
