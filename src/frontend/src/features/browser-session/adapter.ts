/**
 * SelkiesClientAdapter
 *
 * Thin adapter running inside the Selkies iframe (or host environment) to:
 * - Redirect signaling to /stream/{profileId}/signal
 * - Intercept and handle Gateway rtc_config and ice_restart control frames
 * - Preserve Gateway iceServers and iceTransportPolicy on setConfiguration (d022)
 * - Preserve official Selkies HELLO, client_tab_id, and resume_key
 * - Resolve duplicated tab conflicts via Web Locks without kicking the original tab (AC-002)
 * - Lock remote display resolution & DPR against external resize (AC-004)
 * - Block client activity/visibility frames to Gateway (AC-004, Plan 9.3)
 * - Enforce target="_blank" rel="noopener" on new windows
 * - Report diagnostic metrics and lifecycle state changes
 */

export const DATA_CHANNEL_HISTORY_LIMIT = 500;
export const RESTART_OFFER_HISTORY_LIMIT = 20;

function pushBounded(target: any[], value: unknown, limit: number): void {
  target.push(value);
  if (target.length > limit) {
    target.splice(0, target.length - limit);
  }
}

export function installSelkiesClientAdapter(
  targetWindow: Window = window,
  profileId: string = "default"
): void {
  const win = targetWindow as any;
  if (win.__cbrowserShimInstalled) {
    return;
  }
  win.__cbrowserShimInstalled = true;
  win.__cbrowserIdentityGuard = true;
  win.__cbrowserAdapterSource = "features/browser-session/adapter.ts";
  win.__SELKIES_STREAMING_MODE__ = "webrtc";

  // Lock remote display resolution (AC-004)
  win.enable_resize = false;
  win.manual_resolution = true;
  win.manualResolution = true;

  // Enforce rel="noopener" for new windows and tabs
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

  const NativeWebSocket = win.WebSocket;
  const NativeRTCPeerConnection = win.RTCPeerConnection;
  const NativeSetConfiguration =
    NativeRTCPeerConnection?.prototype?.setConfiguration;
  const NativeDataChannelSend = win.RTCDataChannel?.prototype?.send;

  win.__NativeWebSocket = NativeWebSocket;
  win.__NativeRTCPeerConnection = NativeRTCPeerConnection;
  win.__sentDataChannelMessages = [];

  // Filter DataChannel messages (AC-004: block resize packets 'r,width,height')
  if (win.RTCDataChannel?.prototype) {
    win.RTCDataChannel.prototype.send = function (data: any) {
      if (typeof data === "string" && data.startsWith("r,")) {
        return;
      }
      if (Array.isArray(win.__sentDataChannelMessages)) {
        pushBounded(
          win.__sentDataChannelMessages,
          data,
          DATA_CHANNEL_HISTORY_LIMIT
        );
      }
      if (NativeDataChannelSend) {
        return NativeDataChannelSend.call(this, data);
      }
    };
  }

  let activePC: any = null;
  let latestRtcConfig: any = null;
  let activeWS: any = null;
  let heldId: string | null = null;
  const acquisitions = new Map<string, Promise<boolean>>();

  win.__applyGatewayRtcConfig = (config: any) => {
    latestRtcConfig = config;
    win.__latestRtcConfig = config;
    if (activePC && typeof activePC.setConfiguration === "function") {
      try {
        activePC.setConfiguration(config);
      } catch {
        // Ignored
      }
    }
  };

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

  // RTCPeerConnection wrapper (d022: preserves Gateway iceServers and iceTransportPolicy)
  if (NativeRTCPeerConnection) {
    win.RTCPeerConnection = function (...args: any[]) {
      const config = args[0] ? Object.assign({}, args[0]) : {};
      if (latestRtcConfig) {
        if (latestRtcConfig.iceServers) {
          config.iceServers = latestRtcConfig.iceServers;
        }
        if (latestRtcConfig.iceTransportPolicy) {
          config.iceTransportPolicy = latestRtcConfig.iceTransportPolicy;
        }
      }
      const params = new URLSearchParams(win.location?.search || "");
      if (
        params.get("webrtc_mode") === "relay-only" ||
        win.__CBROWSER_WEBRTC_MODE__ === "relay-only" ||
        latestRtcConfig?.iceTransportPolicy === "relay"
      ) {
        config.iceTransportPolicy = "relay";
      }

      const pc = new NativeRTCPeerConnection(config);
      activePC = pc;
      win.__activePC = pc;
      // Only the live peer connection is retained; stale PCs are not
      // reachable from diagnostics and must not accumulate on reconnects.
      win.__pcs = [pc];

      if (typeof pc.addEventListener === "function") {
        pc.addEventListener("datachannel", (event: any) => {
          if (event.channel && event.channel.label === "input") {
            win.__inputChannel = event.channel;
          }
        });

        const notifyState = () => {
          const parentOrigin = win.location?.origin;
          if (win.parent && win.parent !== win && parentOrigin) {
            win.parent.postMessage(
              {
                type: "CBROWSER_PC_STATE",
                connectionState: pc.connectionState,
                iceConnectionState: pc.iceConnectionState,
                signalingState: pc.signalingState,
              },
              parentOrigin
            );
          }
        };
        pc.addEventListener("connectionstatechange", notifyState);
        pc.addEventListener("iceconnectionstatechange", notifyState);
        pc.addEventListener("signalingstatechange", notifyState);
      }

      return pc;
    };

    win.RTCPeerConnection.prototype = NativeRTCPeerConnection.prototype;
    Object.assign(win.RTCPeerConnection, NativeRTCPeerConnection);

    if (NativeSetConfiguration) {
      win.RTCPeerConnection.prototype.setConfiguration = function (config: any) {
        const merged = config ? Object.assign({}, config) : {};
        if (latestRtcConfig) {
          if (latestRtcConfig.iceServers) {
            merged.iceServers = latestRtcConfig.iceServers;
          }
          if (latestRtcConfig.iceTransportPolicy) {
            merged.iceTransportPolicy = latestRtcConfig.iceTransportPolicy;
          }
        }
        const params = new URLSearchParams(win.location?.search || "");
        if (
          params.get("webrtc_mode") === "relay-only" ||
          win.__CBROWSER_WEBRTC_MODE__ === "relay-only" ||
          latestRtcConfig?.iceTransportPolicy === "relay"
        ) {
          merged.iceTransportPolicy = "relay";
        }
        return NativeSetConfiguration.call(this, merged);
      };
    }
  }

  // WebSocket proxy wrapper
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
      win.__last_ws = ws;

      const nativeSend = ws.send.bind(ws);
      (ws as any)._nativeSend = nativeSend;

      ws.send = function (data: any) {
        // Handle HELLO client with tab collision prevention
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
                // Collision detected: generate new tab ID and reconnect
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
              ws.close(1008, "tab_identity_unavailable");
            });
          return;
        }

        // AC-004: Drop visibility / activity frames
        if (
          typeof data === "string" &&
          data.includes('"cbrowser"') &&
          data.includes('"activity"')
        ) {
          return;
        }

        nativeSend(data);
      };

      let userOnMessage: any = null;
      Object.defineProperty(ws, "onmessage", {
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
      const wrappedListeners = new Map<any, any>();

      ws.addEventListener = function (
        type: string,
        listener: any,
        options?: any
      ) {
        if (type === "message" && typeof listener === "function") {
          const wrapped = function (this: any, event: any) {
            const data = event.data;
            if (typeof data === "string" && data.includes('"cbrowser"')) {
              try {
                const parsed = JSON.parse(data);
                if (parsed && parsed.cbrowser) {
                  return; // Don't forward cbrowser control frames to Selkies
                }
              } catch {
                // Ignore parse errors
              }
            }
            return listener.call(this, event);
          };
          wrappedListeners.set(listener, wrapped);
          return origAddEventListener(type, wrapped, options);
        }
        return origAddEventListener(type, listener, options);
      };

      ws.removeEventListener = function (
        type: string,
        listener: any,
        options?: any
      ) {
        if (type === "message" && wrappedListeners.has(listener)) {
          const wrapped = wrappedListeners.get(listener);
          wrappedListeners.delete(listener);
          return origRemoveEventListener(type, wrapped, options);
        }
        return origRemoveEventListener(type, listener, options);
      };

      // Handle Gateway control frames
      origAddEventListener("message", async (event: any) => {
        const data = event.data;
        if (typeof data === "string" && data.includes('"cbrowser"')) {
          try {
            const parsed = JSON.parse(data);
            if (parsed && parsed.cbrowser) {
              if (parsed.cbrowser === "rtc_config") {
                win.__applyGatewayRtcConfig(parsed.rtc_config);
              } else if (parsed.cbrowser === "ice_restart") {
                const restartOffers =
                  win.__restartOffers || (win.__restartOffers = []);
                let offerUfrag: string | null = null;
                if (parsed.offer && parsed.offer.sdp) {
                  for (const line of parsed.offer.sdp.split("\n")) {
                    const trim = line.trim();
                    if (trim.startsWith("a=ice-ufrag:")) {
                      offerUfrag = trim.split(":", 2)[1]?.trim() || null;
                      break;
                    }
                  }
                }
                pushBounded(
                  restartOffers,
                  {
                    generation: parsed.generation,
                    ufrag: offerUfrag,
                    offer: parsed.offer,
                  },
                  RESTART_OFFER_HISTORY_LIMIT
                );

                if (parsed.rtc_config) {
                  win.__applyGatewayRtcConfig(parsed.rtc_config);
                }

                if (activePC) {
                  try {
                    await activePC.setRemoteDescription(parsed.offer);
                    const answer = await activePC.createAnswer();
                    await activePC.setLocalDescription(answer);

                    if (activePC.iceGatheringState !== "complete") {
                      await new Promise<void>((resolve) => {
                        const check = () => {
                          if (activePC.iceGatheringState === "complete") {
                            activePC.removeEventListener(
                              "icegatheringstatechange",
                              check
                            );
                            resolve();
                          }
                        };
                        activePC.addEventListener(
                          "icegatheringstatechange",
                          check
                        );
                        setTimeout(resolve, 3000);
                      });
                    }

                    const answerPayload = {
                      cbrowser: "ice_restart_answer",
                      generation: parsed.generation,
                      sdp: {
                        type: activePC.localDescription?.type || "answer",
                        sdp: activePC.localDescription?.sdp || "",
                      },
                    };
                    nativeSend(JSON.stringify(answerPayload));
                  } catch (err) {
                    console.error("ice_restart failure:", err);
                  }
                }
              }
              return;
            }
          } catch {
            // Ignored
          }
        }
        if (userOnMessage) {
          userOnMessage.call(ws, event);
        }
      });

      // Post close events to parent window
      ws.addEventListener("close", (e: any) => {
        const parentOrigin = win.location?.origin;
        if (win.parent && win.parent !== win && parentOrigin) {
          win.parent.postMessage(
            {
              type: "CBROWSER_WS_CLOSE",
              code: e.code,
              reason: e.reason,
            },
            parentOrigin
          );
        }
      });

      return ws;
    };

    win.WebSocket.prototype = NativeWebSocket.prototype;
    Object.assign(win.WebSocket, NativeWebSocket);
  }

  // Diagnostics method
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

  // AC-007: Page Lifecycle and bfcache reactivation handler
  const handleReactivate = () => {
    const pcBroken =
      activePC &&
      (activePC.connectionState === "failed" ||
        activePC.connectionState === "closed");
    const wsBroken = activeWS && activeWS.readyState > 1; // CLOSING or CLOSED
    if (pcBroken || wsBroken) {
      const parentOrigin = win.location?.origin;
      if (win.parent && win.parent !== win && parentOrigin) {
        win.parent.postMessage({ type: "CBROWSER_LIFECYCLE_STALE" }, parentOrigin);
      }
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
