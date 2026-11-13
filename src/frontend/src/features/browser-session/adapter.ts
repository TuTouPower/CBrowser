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

import type {
  SelkiesAudioStats,
  SelkiesCandidatePairStats,
  SelkiesStats,
  SelkiesVideoStats,
} from "./types";

type SelkiesWindow = Window &
  typeof globalThis & {
    __SELKIES_STREAMING_MODE__?: string;
    enable_resize?: boolean;
    manual_resolution?: boolean;
    manualResolution?: boolean;
    __CBROWSER_PROFILE_ID__?: string;
    __getWebRTCStats?: () => Promise<SelkiesStats | null>;
  };

type DataChannelPayload = string | Blob | ArrayBuffer | ArrayBufferView;
type WebSocketPayload = string | ArrayBufferLike | Blob | ArrayBufferView;

const installedWindows = new WeakSet<object>();

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : null;
}

function numberField(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function nullableNumberField(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringField(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function pairFrom(
  stat: Record<string, unknown>,
  report: ReadonlyMap<string, unknown>
): SelkiesCandidatePairStats {
  const local = asRecord(report.get(stringField(stat.localCandidateId) ?? ""));
  const remote = asRecord(report.get(stringField(stat.remoteCandidateId) ?? ""));
  return {
    localType: local ? stringField(local.candidateType) : null,
    remoteType: remote ? stringField(remote.candidateType) : null,
    remoteAddress: remote
      ? stringField(remote.ip) ?? stringField(remote.address)
      : null,
    remotePort: remote ? nullableNumberField(remote.port) : null,
    remoteUfrag: remote ? stringField(remote.usernameFragment) : null,
    bytesReceived: numberField(stat.bytesReceived),
    roundTripTime:
      numberField(stat.currentRoundTripTime) ||
      numberField(stat.roundTripTime),
  };
}

export function installSelkiesClientAdapter(
  targetWindow: Window = window,
  profileId: string
): void {
  const win = targetWindow as SelkiesWindow;
  // Strict viewer identity (t069): the install-time profileId — passed
  // by the selkies adapter entry from the host page's documented
  // ?profileId= channel — is the only identity source. A missing id or
  // a global __CBROWSER_PROFILE_ID__ injection is rejected outright;
  // there is no "default" profile and no other fallback.
  if (!profileId) {
    throw new Error(
      "installSelkiesClientAdapter: a non-empty profileId is required"
    );
  }
  if (win.__CBROWSER_PROFILE_ID__ !== undefined) {
    throw new Error(
      "installSelkiesClientAdapter: __CBROWSER_PROFILE_ID__ global injection is not accepted"
    );
  }
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
      (e: MouseEvent) => {
        const element = e.target as Element | null;
        const anchor =
          element && typeof element.closest === "function"
            ? element.closest("a")
            : null;
        if (anchor && anchor.target === "_blank") {
          const rel = anchor.getAttribute("rel") || "";
          if (!rel.includes("noopener")) {
            anchor.setAttribute("rel", rel ? `${rel} noopener` : "noopener");
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

  const NativeWebSocket: typeof WebSocket | undefined = win.WebSocket;
  const NativeRTCPeerConnection: typeof RTCPeerConnection | undefined =
    win.RTCPeerConnection;
  const NativeDataChannelSend = win.RTCDataChannel?.prototype?.send;

  if (win.RTCDataChannel?.prototype) {
    win.RTCDataChannel.prototype.send = function (
      this: RTCDataChannel,
      data: DataChannelPayload
    ) {
      if (typeof data === "string" && data.startsWith("r,")) {
        return;
      }
      if (NativeDataChannelSend) {
        Reflect.apply(NativeDataChannelSend, this, [data]);
      }
    };
  }

  let activePC: RTCPeerConnection | null = null;
  let activeWS: WebSocket | null = null;
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
          (lock: Lock | null) => {
            if (!lock) {
              resolve(false);
              return;
            }
            heldId = id;
            resolve(true);
            return new Promise<void>(() => {}); // Hold lock across signaling reconnects
          }
        )
        .catch(reject);
    });

    acquisitions.set(id, pending);
    pending.finally(() => acquisitions.delete(id)).catch(() => {});
    return pending;
  }

  if (NativeRTCPeerConnection) {
    class ShimRTCPeerConnection extends NativeRTCPeerConnection {
      constructor(configuration?: RTCConfiguration) {
        const config: RTCConfiguration = configuration
          ? Object.assign({}, configuration)
          : {};
        // Selkies defaults to Google's public STUN server. This deployment is
        // ICE-lite over a loopback-only media path (ADR 013), so external STUN
        // both stalls setup and yields peer-reflexive candidates.
        config.iceServers = [];
        super(config);
        activePC = this;

        if (typeof this.addEventListener === "function") {
          const notifyState = () => {
            postToParent({
              type: "CBROWSER_PC_STATE",
              connectionState: this.connectionState,
              iceConnectionState: this.iceConnectionState,
              signalingState: this.signalingState,
            });
          };
          this.addEventListener("connectionstatechange", notifyState);
          this.addEventListener("iceconnectionstatechange", notifyState);
          this.addEventListener("signalingstatechange", notifyState);
        }
      }
    }

    win.RTCPeerConnection = ShimRTCPeerConnection;
  }

  if (NativeWebSocket) {
    const BaseWebSocket = NativeWebSocket;
    class ShimWebSocket extends BaseWebSocket {
      constructor(url: string | URL, protocols?: string | string[]) {
        const u = new URL(url, win.location?.href || "http://localhost");
        // Identity comes only from the install-time profileId closure
        // (t069): query parameters and globals in this page are never
        // re-read as identity sources.
        const resolvedProfileId = profileId;

        if (
          u.pathname.includes("/signaling") ||
          u.pathname.endsWith("/api/ws") ||
          u.pathname.includes("/stream/")
        ) {
          u.protocol = win.location?.protocol === "https:" ? "wss:" : "ws:";
          u.host = win.location?.host || "localhost";
          u.pathname = `/stream/${encodeURIComponent(resolvedProfileId)}/signal`;
        }

        super(u.toString(), protocols);
        activeWS = this;

        const nativeSend = this.send.bind(this);

        this.send = (data: WebSocketPayload): void => {
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
                if (this.readyState !== BaseWebSocket.OPEN) return;
                if (!acquired) {
                  const newId =
                    win.crypto?.randomUUID?.() ||
                    `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
                  win.sessionStorage?.setItem("selkies_tab_id", newId);
                  this.close(1000, "tab_collision_remap");
                  return;
                }
                nativeSend(data);
              })
              .catch(() => {
                postToParent({ type: "CBROWSER_WEB_LOCKS_UNAVAILABLE" });
                this.close(1008, "tab_identity_unavailable");
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

        this.addEventListener("close", (e: CloseEvent) => {
          postToParent({
            type: "CBROWSER_WS_CLOSE",
            code: e.code,
            reason: e.reason,
          });
        });
      }
    }

    win.WebSocket = ShimWebSocket;
  }

  win.__getWebRTCStats = async (): Promise<SelkiesStats | null> => {
    const pc = activePC;
    if (!pc || typeof pc.getStats !== "function") return null;

    try {
      const report: ReadonlyMap<string, unknown> = await pc.getStats();
      let video: SelkiesVideoStats | null = null;
      let audio: SelkiesAudioStats | null = null;
      let pair: SelkiesCandidatePairStats | null = null;

      for (const raw of report.values()) {
        const stat = asRecord(raw);
        if (!stat) continue;
        if (stat.type === "inbound-rtp") {
          if (stat.kind === "video") {
            video = {
              framesDecoded: numberField(stat.framesDecoded),
              keyFramesDecoded: numberField(stat.keyFramesDecoded),
              bytesReceived: numberField(stat.bytesReceived),
              packetsLost: numberField(stat.packetsLost),
              packetsReceived: numberField(stat.packetsReceived),
            };
          } else if (stat.kind === "audio") {
            audio = {
              totalAudioEnergy: numberField(stat.totalAudioEnergy),
              bytesReceived: numberField(stat.bytesReceived),
              packetsReceived: numberField(stat.packetsReceived),
              packetsLost: numberField(stat.packetsLost),
              trackIdentifier: stringField(stat.trackIdentifier),
            };
          }
        } else if (
          stat.type === "candidate-pair" &&
          (stat.selected === true || stat.nominated === true || stat.state === "succeeded")
        ) {
          pair = pairFrom(stat, report);
        } else if (
          stat.type === "transport" &&
          stat.selectedCandidatePairId &&
          !pair
        ) {
          const selected = asRecord(
            report.get(stringField(stat.selectedCandidatePairId) ?? "")
          );
          if (selected) {
            pair = pairFrom(selected, report);
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
    win.addEventListener("pageshow", (event: PageTransitionEvent) => {
      if (event.persisted) handleReactivate();
    });
  }
}
