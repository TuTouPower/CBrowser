/**
 * SelkiesClientAdapter
 *
 * Thin adapter running inside the Selkies iframe to:
 * - Redirect signaling to /stream/{profileId}/signal
 * - Preserve official Selkies HELLO, client_tab_id, and resume_key
 * - Resolve duplicated tab conflicts via Web Locks without kicking the original tab
 * - Lock remote display resolution & DPR against external resize
 * - Block client resize/activity frames that must not reach the Gateway
 * - Enforce target="_blank" rel="noopener" on new windows
 * - Report diagnostic metrics and lifecycle state changes to the host page
 *
 * Production contract with the host page:
 * - Host calls `window.__getWebRTCStats()` for session diagnostics.
 * - Iframe posts CBROWSER_PC_STATE, CBROWSER_WS_CLOSE, CBROWSER_LIFECYCLE_STALE
 *   and CBROWSER_WEB_LOCKS_UNAVAILABLE messages to `window.parent`.
 * No other globals are exposed for tests; probes are injected by the test suite.
 */

const installedWindows = new WeakSet<object>();

export function installSelkiesClientAdapter(
  targetWindow: Window = window,
  profileId: string = "default"
): void {
  const win = targetWindow as any;
  if (installedWindows.has(win)) {
    return;
  }
  installedWindows.add(win);
  win.__SELKIES_STREAMING_MODE__ = "webrtc";

  // Lock remote display resolution against client-side resize.
  win.enable_resize = false;
  win.manual_resolution = true;
  win.manualResolution = true;

  // Enforce rel="noopener" for new windows and tabs.
  if (typeof win.open === "function") {
    const origOpen = win.open.bind(win);
    win.open = function (url?: string | URL, target?: string, features?: string) {
      const tgt = target || "_blank";
      const feat = features ? `${features},noopener` : "noopener";
      return origOpen(url, tgt, feat);
    };
  }
  if (win.document && typeof win.document.addEventListener === "function") {
    win.document.addEventListener(
      "click",
      (e: any) => {
        const a = e.target && e.target.closest ? e.target.closest("a") : null;
        if (a && a.target === "_blank") {
          const rel = a.getAttribute("rel") || "";
          if (!rel.includes("noopener")) {
            a.setAttribute("rel", rel ? `${rel} noopener` : "noopener");
          }
        }
      },
      true
    );
  }

  // Guard against keyboard event interception when the iframe does not have active focus
  if (typeof win.addEventListener === "function") {
    const isIframeFocused = (): boolean => {
      try {
        if (win.parent && win.parent !== win && win.parent.document && win.frameElement) {
          if (win.parent.document.activeElement !== win.frameElement) {
            return false;
          }
        }
      } catch {
        // Cross-origin / sandbox access boundary: fall back to inner document check
      }

      try {
        return Boolean(win.document && typeof win.document.hasFocus === "function" && win.document.hasFocus());
      } catch {
        return true;
      }
    };

    const guardKeyEvent = (e: KeyboardEvent) => {
      if (!isIframeFocused()) {
        e.stopImmediatePropagation();
      }
    };

    win.addEventListener("keydown", guardKeyEvent, true);
    win.addEventListener("keyup", guardKeyEvent, true);
  }

  const NativeWebSocket = win.WebSocket;
  const NativeRTCPeerConnection = win.RTCPeerConnection;
  const NativeDataChannelSend = win.RTCDataChannel?.prototype?.send;

  if (win.RTCDataChannel?.prototype) {
    win.RTCDataChannel.prototype.send = function (data: any) {
      if (typeof data === "string" && data.startsWith("r,")) {
        return;
      }
      if (NativeDataChannelSend) {
        return NativeDataChannelSend.call(this, data);
      }
    };
  }

  let activePC: any = null;
  let activeWS: any = null;
  let heldId: string | null = null;
  const acquisitions = new Map<string, Promise<boolean>>();

  function postToParent(message: Record<string, unknown>): void {
    const parentOrigin = win.location?.origin;
    if (win.parent && win.parent !== win && parentOrigin) {
      win.parent.postMessage(message, parentOrigin);
    }
  }

  function acquireLock(id: string): Promise<boolean> {
    if (heldId === id) return Promise.resolve(true);
    if (acquisitions.has(id)) return acquisitions.get(id)!;

    const pending = new Promise<boolean>((resolve, reject) => {
      if (!win.navigator?.locks?.request) {
        reject(new Error("Web Locks required"));
        return;
      }
      win.navigator.locks
        .request(
          `cbrowser_tab_lock_${id}`,
          { ifAvailable: true },
          (lock: any) => {
            if (!lock) {
              resolve(false);
              return;
            }
            heldId = id;
            resolve(true);
            return new Promise(() => {}); // Hold lock across signaling reconnects
          }
        )
        .catch(reject);
    });

    acquisitions.set(id, pending);
    pending.finally(() => acquisitions.delete(id)).catch(() => {});
    return pending;
  }

  if (NativeRTCPeerConnection) {
    win.RTCPeerConnection = function (...args: any[]) {
      const config = args[0] ? Object.assign({}, args[0]) : {};
      const pc = new NativeRTCPeerConnection(config);
      activePC = pc;

      if (typeof pc.addEventListener === "function") {
        const notifyState = () => {
          postToParent({
            type: "CBROWSER_PC_STATE",
            connectionState: pc.connectionState,
            iceConnectionState: pc.iceConnectionState,
            signalingState: pc.signalingState,
          });
        };
        pc.addEventListener("connectionstatechange", notifyState);
        pc.addEventListener("iceconnectionstatechange", notifyState);
        pc.addEventListener("signalingstatechange", notifyState);
      }

      return pc;
    };

    win.RTCPeerConnection.prototype = NativeRTCPeerConnection.prototype;
    Object.assign(win.RTCPeerConnection, NativeRTCPeerConnection);
  }

  if (NativeWebSocket) {
    win.WebSocket = function (url: string, protocols?: any) {
      const u = new URL(url, win.location?.href || "http://localhost");
      const params = new URLSearchParams(win.location?.search || "");
      const resolvedProfileId =
        params.get("profileId") ||
        params.get("profile_id") ||
        win.__CBROWSER_PROFILE_ID__ ||
        profileId ||
        "default";

      if (
        u.pathname.includes("/signaling") ||
        u.pathname.endsWith("/api/ws") ||
        u.pathname.includes("/stream/")
      ) {
        u.protocol = win.location?.protocol === "https:" ? "wss:" : "ws:";
        u.host = win.location?.host || "localhost";
        u.pathname = `/stream/${encodeURIComponent(resolvedProfileId)}/signal`;
      }

      const ws =
        protocols !== undefined
          ? new NativeWebSocket(u.toString(), protocols)
          : new NativeWebSocket(u.toString());
      activeWS = ws;

      const nativeSend = ws.send.bind(ws);

      ws.send = function (data: any) {
        if (typeof data === "string" && data.startsWith("HELLO client ")) {
          let id = win.sessionStorage?.getItem("selkies_tab_id");
          if (!id) {
            id =
              win.crypto?.randomUUID?.() ||
              `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
            win.sessionStorage?.setItem("selkies_tab_id", id);
          }
          acquireLock(id)
            .then((acquired) => {
              if (ws.readyState !== NativeWebSocket.OPEN) return;
              if (!acquired) {
                const newId =
                  win.crypto?.randomUUID?.() ||
                  `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
                win.sessionStorage?.setItem("selkies_tab_id", newId);
                ws.close(1000, "tab_collision_remap");
                return;
              }
              nativeSend(data);
            })
            .catch(() => {
              postToParent({ type: "CBROWSER_WEB_LOCKS_UNAVAILABLE" });
              ws.close(1008, "tab_identity_unavailable");
            });
          return;
        }

        if (
          typeof data === "string" &&
          data.includes('"cbrowser"') &&
          data.includes('"activity"')
        ) {
          return;
        }

        nativeSend(data);
      };

      ws.addEventListener("close", (e: any) => {
        postToParent({
          type: "CBROWSER_WS_CLOSE",
          code: e.code,
          reason: e.reason,
        });
      });

      return ws;
    };

    win.WebSocket.prototype = NativeWebSocket.prototype;
    Object.assign(win.WebSocket, NativeWebSocket);
  }

  win.__getWebRTCStats = async () => {
    const pc = activePC;
    if (!pc || typeof pc.getStats !== "function") return null;

    try {
      const report = await pc.getStats();
      let video: any = null;
      let audio: any = null;
      let pair: any = null;

      for (const stat of report.values()) {
        if (stat.type === "inbound-rtp") {
          if (stat.kind === "video") {
            video = {
              framesDecoded: stat.framesDecoded || 0,
              keyFramesDecoded: stat.keyFramesDecoded || 0,
              bytesReceived: stat.bytesReceived || 0,
              packetsLost: stat.packetsLost || 0,
              packetsReceived: stat.packetsReceived || 0,
            };
          } else if (stat.kind === "audio") {
            audio = {
              totalAudioEnergy: stat.totalAudioEnergy || 0,
              bytesReceived: stat.bytesReceived || 0,
              packetsReceived: stat.packetsReceived || 0,
              packetsLost: stat.packetsLost || 0,
              trackIdentifier: stat.trackIdentifier || null,
            };
          }
        } else if (
          stat.type === "candidate-pair" &&
          (stat.selected || stat.nominated || stat.state === "succeeded")
        ) {
          const local = report.get(stat.localCandidateId);
          const remote = report.get(stat.remoteCandidateId);
          pair = {
            localType: local ? local.candidateType : null,
            remoteType: remote ? remote.candidateType : null,
            remoteAddress: remote ? remote.ip || remote.address : null,
            remotePort: remote ? remote.port : null,
            remoteUfrag: remote ? remote.usernameFragment : null,
            bytesReceived: stat.bytesReceived || 0,
            roundTripTime: stat.currentRoundTripTime || stat.roundTripTime || 0,
          };
        } else if (
          stat.type === "transport" &&
          stat.selectedCandidatePairId &&
          !pair
        ) {
          const p = report.get(stat.selectedCandidatePairId);
          if (p) {
            const local = report.get(p.localCandidateId);
            const remote = report.get(p.remoteCandidateId);
            pair = {
              localType: local ? local.candidateType : null,
              remoteType: remote ? remote.candidateType : null,
              remoteAddress: remote ? remote.ip || remote.address : null,
              remotePort: remote ? remote.port : null,
              remoteUfrag: remote ? remote.usernameFragment : null,
              bytesReceived: p.bytesReceived || 0,
              roundTripTime:
                p.currentRoundTripTime || p.roundTripTime || 0,
            };
          }
        }
      }

      return {
        video,
        audio,
        pair,
        tab_id: win.sessionStorage?.getItem("selkies_tab_id"),
        connected:
          pc.connectionState === "connected" ||
          pc.iceConnectionState === "connected",
        connectionState: pc.connectionState,
        iceConnectionState: pc.iceConnectionState,
        signalingState: pc.signalingState,
      };
    } catch {
      return null;
    }
  };

  const handleReactivate = () => {
    const pcBroken =
      activePC &&
      (activePC.connectionState === "failed" ||
        activePC.connectionState === "closed");
    const wsBroken = activeWS && activeWS.readyState > 1;
    if (pcBroken || wsBroken) {
      postToParent({ type: "CBROWSER_LIFECYCLE_STALE" });
    }
  };

  if (win.document && typeof win.document.addEventListener === "function") {
    win.document.addEventListener("resume", handleReactivate);
  }
  if (typeof win.addEventListener === "function") {
    win.addEventListener("pageshow", (event: any) => {
      if (event.persisted) handleReactivate();
    });
  }
}
