import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import React from "react";
import { BrowserSessionView } from "./BrowserSessionView";
import { installSelkiesClientAdapter } from "./adapter";
import type { BrowserSessionViewProps } from "./types";
import { I18nProvider } from "../../i18n";

function renderView(props: BrowserSessionViewProps) {
  return render(
    <I18nProvider>
      <BrowserSessionView {...props} />
    </I18nProvider>
  );
}

function dispatchIframeMessage(
  iframe: HTMLIFrameElement,
  data: Record<string, unknown>,
  overrides: { origin?: string; source?: MessageEventSource | null } = {}
) {
  act(() => {
    window.dispatchEvent(
      new MessageEvent("message", {
        data,
        origin: overrides.origin ?? window.location.origin,
        source:
          overrides.source === undefined
            ? (iframe.contentWindow as unknown as MessageEventSource)
            : overrides.source,
      })
    );
  });
}

function iframeSrc() {
  return screen.getByTestId("browser-session-iframe").getAttribute("src") || "";
}

describe("BrowserSessionView (AC-003, AC-007, AC-004)", () => {
  const profileId = "profile-test-123";

  beforeEach(() => {
    localStorage.setItem("cbm.locale", "zh");
    vi.restoreAllMocks();
  });

  afterEach(() => {
    localStorage.clear();
    vi.clearAllTimers();
  });

  it("renders iframe pointing to selkies with profileId query param", () => {
    renderView({ profileId });
    const iframe = screen.getByTestId("browser-session-iframe") as HTMLIFrameElement;
    expect(iframe).toBeDefined();
    expect(iframe.src).toContain(`/selkies/index.html?profileId=${profileId}`);
  });

  it("AC-003: unmounting component closes viewer but does NOT call profile stop or mutate desired-state", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const { unmount } = renderView({ profileId });

    unmount();

    const stopCalls = fetchSpy.mock.calls.filter(([url, opts]) => {
      const u = String(url);
      const m = opts?.method?.toUpperCase() || "GET";
      return (
        u.includes("desired-state") ||
        u.includes("/stop") ||
        (m === "PATCH" && u.includes("/runtime"))
      );
    });
    expect(stopCalls).toHaveLength(0);
  });

  it("AC-007: displays runtime_not_ready stage with reconnect and status actions", async () => {
    const onCheckStatus = vi.fn();
    renderView({
      profileId,
      initialStage: "runtime_not_ready",
      errorMessage: "Profile container is stopped",
      onCheckRuntimeStatus: onCheckStatus,
    });

    expect(screen.getByTestId("session-stage-title").textContent).toContain("运行时未就绪");
    expect(screen.getByTestId("session-error-message").textContent).toContain("Profile container is stopped");

    const reconnectBtn = screen.getByTestId("session-reconnect-btn");
    expect(reconnectBtn).toBeDefined();

    const statusBtn = screen.getByTestId("session-view-status-btn");
    expect(statusBtn).toBeDefined();
    fireEvent.click(statusBtn);
    expect(onCheckStatus).toHaveBeenCalledTimes(1);
  });

  it("A10: stopping stage is explicit and offers status without reconnecting", () => {
    const onCheckStatus = vi.fn();
    renderView({
      profileId,
      initialStage: "stopping",
      onCheckRuntimeStatus: onCheckStatus,
    });

    expect(screen.getByTestId("session-stage-title").textContent).toContain(
      "正在停止会话"
    );
    expect(screen.queryByTestId("session-reconnect-btn")).toBeNull();
    fireEvent.click(screen.getByTestId("session-view-status-btn"));
    expect(onCheckStatus).toHaveBeenCalledTimes(1);
  });

  it("A10: error stage is explicit and offers reconnect plus status", () => {
    renderView({
      profileId,
      initialStage: "error",
      errorMessage: "Runtime failed",
    });

    expect(screen.getByTestId("session-stage-title").textContent).toContain(
      "会话错误"
    );
    expect(screen.getByTestId("session-error-message").textContent).toContain(
      "Runtime failed"
    );
    expect(screen.getByTestId("session-reconnect-btn")).toBeDefined();
  });

  it("AC-007: displays signaling_failed stage with diagnostics and reconnect action", () => {
    renderView({
      profileId,
      initialStage: "signaling_failed",
      errorMessage: "WebSocket connection closed (1006)",
    });

    expect(screen.getByTestId("session-stage-title").textContent).toContain("信令连接失败");
    expect(screen.getByTestId("session-reconnect-btn")).toBeDefined();
  });

  it("AC-007: displays ice_failed stage with RTCPeerConnection metrics and candidate pair", () => {
    renderView({
      profileId,
      initialStage: "ice_failed",
      diagnostics: {
        stage: "ice_failed",
        profileId,
        connectionState: "failed",
        iceConnectionState: "failed",
        signalingState: "stable",
        selectedPair: {
          localType: "host",
          remoteType: "relay",
          remoteAddress: "127.0.0.1",
          remotePort: 3478,
          remoteUfrag: "ufrag1",
          roundTripTime: 0.045,
          bytesReceived: 1024,
        },
        roundTripTime: 45,
        packetsLost: 12,
        packetsReceived: 250,
        framesDecoded: 0,
      },
    });

    expect(screen.getByTestId("session-stage-title").textContent).toContain("ICE 协商失败");
    expect(screen.getByTestId("diag-ice-state").textContent).toBe("failed");
    expect(screen.getByTestId("diag-rtt").textContent).toContain("45 ms");
    expect(screen.getByTestId("diag-packets-lost").textContent).toBe("12");
    expect(screen.getByTestId("diag-candidate-type").textContent).toContain("relay");
  });

  it("AC-007: displays media_no_frames stage when connected but no frames decoded", () => {
    renderView({
      profileId,
      initialStage: "media_no_frames",
      diagnostics: {
        stage: "media_no_frames",
        profileId,
        connectionState: "connected",
        iceConnectionState: "connected",
        signalingState: "stable",
        framesDecoded: 0,
        packetsReceived: 15,
      },
    });

    expect(screen.getByTestId("session-stage-title").textContent).toContain("媒体未产生画面");
    expect(screen.getByTestId("session-reconnect-btn")).toBeDefined();
    expect(screen.getByTestId("diag-frames-decoded").textContent).toBe("0");
  });

  it("AC-007: reconnect button performs a real iframe reload", async () => {
    renderView({ profileId, initialStage: "ice_failed" });
    expect(iframeSrc()).toContain("_k=0");

    fireEvent.click(screen.getByTestId("session-reconnect-btn"));

    await waitFor(() => {
      expect(iframeSrc()).toContain("_k=1");
    });
  });

  it("AC-007: CBROWSER_PC_STATE iceConnectionState=failed migrates stage and diagnostics", async () => {
    const onCheckStatus = vi.fn();
    renderView({
      profileId,
      initialStage: "media_waiting",
      onCheckRuntimeStatus: onCheckStatus,
    });
    const iframe = screen.getByTestId("browser-session-iframe") as HTMLIFrameElement;

    dispatchIframeMessage(iframe, {
      type: "CBROWSER_PC_STATE",
      connectionState: "failed",
      iceConnectionState: "failed",
      signalingState: "stable",
    });

    await waitFor(() => {
      expect(screen.getByTestId("session-stage-title").textContent).toContain(
        "ICE 协商失败"
      );
    });
    expect(screen.getByTestId("diag-ice-state").textContent).toBe("failed");
    expect(screen.getByTestId("diag-conn-state").textContent).toBe("failed");
    expect(screen.getByTestId("session-reconnect-btn")).toBeDefined();
    expect(screen.getByTestId("session-view-status-btn")).toBeDefined();
  });

  it("AC-007: a transient ICE disconnect that recovers is not reported as ICE failure", async () => {
    renderView({ profileId, initialStage: "connected" });
    const iframe = screen.getByTestId("browser-session-iframe") as HTMLIFrameElement;

    dispatchIframeMessage(iframe, {
      type: "CBROWSER_PC_STATE",
      connectionState: "disconnected",
      iceConnectionState: "disconnected",
      signalingState: "stable",
    });
    await new Promise((resolve) => setTimeout(resolve, 1000));
    expect(screen.queryByText("ICE 协商失败")).toBeNull();

    dispatchIframeMessage(iframe, {
      type: "CBROWSER_PC_STATE",
      connectionState: "connected",
      iceConnectionState: "connected",
      signalingState: "stable",
    });
    await new Promise((resolve) => setTimeout(resolve, 5500));
    expect(screen.queryByText("ICE 协商失败")).toBeNull();
  }, 12000);

  it("AC-007: a persistent ICE disconnect becomes an ICE failure stage", async () => {
    renderView({ profileId, initialStage: "connected" });
    const iframe = screen.getByTestId("browser-session-iframe") as HTMLIFrameElement;

    dispatchIframeMessage(iframe, {
      type: "CBROWSER_PC_STATE",
      connectionState: "disconnected",
      iceConnectionState: "disconnected",
      signalingState: "stable",
    });

    await waitFor(
      () => {
        expect(screen.getByTestId("session-stage-title").textContent).toContain(
          "ICE 协商失败"
        );
      },
      { timeout: 8000 }
    );
    expect(screen.getByTestId("diag-ice-state").textContent).toBe("disconnected");
  }, 12000);

  it("AC-007: CBROWSER_WS_CLOSE on a live connection triggers a real rebuild", async () => {
    renderView({ profileId, initialStage: "connected" });
    const iframe = screen.getByTestId("browser-session-iframe") as HTMLIFrameElement;

    dispatchIframeMessage(iframe, {
      type: "CBROWSER_WS_CLOSE",
      code: 1006,
      reason: "abnormal",
    });

    await waitFor(
      () => {
        expect(iframeSrc()).toContain("_k=1");
      },
      { timeout: 8000 }
    );
  }, 12000);

  it("AC-007: CBROWSER_LIFECYCLE_STALE triggers a real rebuild and stage migration", async () => {
    renderView({ profileId, initialStage: "connected" });
    const iframe = screen.getByTestId("browser-session-iframe") as HTMLIFrameElement;

    dispatchIframeMessage(iframe, { type: "CBROWSER_LIFECYCLE_STALE" });

    await waitFor(() => {
      expect(iframeSrc()).toContain("_k=1");
    });
    expect(screen.getByTestId("browser-session-view").getAttribute("data-stage")).toBe(
      "reconnecting"
    );
  });

  it("AC-007: bfcache pageshow(persisted) rebuilds a dead connection only", async () => {
    renderView({ profileId, initialStage: "connected" });
    const iframe = screen.getByTestId("browser-session-iframe") as HTMLIFrameElement;
    const frameWindow = iframe.contentWindow as any;

    // Healthy connection after restore: no rebuild.
    frameWindow.__getWebRTCStats = async () => ({ connected: true });
    window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(iframeSrc()).not.toContain("_k=1");

    // Not restored from bfcache: no reactivation check at all.
    frameWindow.__getWebRTCStats = async () => ({ connected: false });
    window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: false }));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(iframeSrc()).not.toContain("_k=1");

    // Restored from bfcache with a dead connection: rebuild.
    window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
    await waitFor(() => {
      expect(iframeSrc()).toContain("_k=1");
    });
  });

  it("AC-007: ignores messages from a forged source or origin", async () => {
    renderView({ profileId, initialStage: "connected" });
    const iframe = screen.getByTestId("browser-session-iframe") as HTMLIFrameElement;

    dispatchIframeMessage(
      iframe,
      { type: "CBROWSER_LIFECYCLE_STALE" },
      { source: null }
    );
    dispatchIframeMessage(
      iframe,
      { type: "CBROWSER_LIFECYCLE_STALE" },
      { origin: "https://evil.example" }
    );

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(iframeSrc()).toContain("_k=0");
    expect(screen.getByTestId("browser-session-view").getAttribute("data-stage")).toBe(
      "connected"
    );

    dispatchIframeMessage(iframe, { type: "CBROWSER_LIFECYCLE_STALE" });
    await waitFor(() => {
      expect(iframeSrc()).toContain("_k=1");
    });
  });
});

describe("SelkiesClientAdapter unit tests (adapter.ts)", () => {
  let fakeWindow: any;
  let nativeSetConfigurationSpy: any;
  let nativeDataChannelSend: any;
  let openSpy: any;

  beforeEach(() => {
    nativeSetConfigurationSpy = vi.fn();
    nativeDataChannelSend = vi.fn();
    openSpy = vi.fn();
    fakeWindow = {
      location: {
        href: "https://cbrowser.local/app",
        search: "?profileId=prof_456",
        protocol: "https:",
        host: "cbrowser.local",
        origin: "https://cbrowser.local",
      },
      sessionStorage: {
        _data: {} as Record<string, string>,
        getItem(k: string) { return this._data[k] || null; },
        setItem(k: string, v: string) { this._data[k] = v; },
        removeItem(k: string) { delete this._data[k]; },
      },
      crypto: {
        randomUUID: () => "uuid-fixed-1234",
      },
      navigator: {
        locks: {
          request: vi.fn(),
        },
      },
      open: openSpy,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      document: {
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      },
      parent: {
        postMessage: vi.fn(),
      },
      WebSocket: class MockWebSocket {
        static OPEN = 1;
        url: string;
        protocols?: any;
        readyState = 1; // OPEN
        sent: any[] = [];
        send = vi.fn((data: any) => {
          this.sent.push(data);
        });
        close = vi.fn();
        addEventListener = vi.fn();
        removeEventListener = vi.fn();
        constructor(url: string, protocols?: any) {
          this.url = url;
          this.protocols = protocols;
        }
      },
      RTCPeerConnection: class MockRTCPeerConnection {
        config: any;
        connectionState = "new";
        iceConnectionState = "new";
        signalingState = "stable";
        listeners: Record<string, Array<(event?: any) => void>> = {};
        setRemoteDescription = vi.fn().mockResolvedValue(undefined);
        createAnswer = vi.fn().mockResolvedValue({ type: "answer", sdp: "v=0..." });
        setLocalDescription = vi.fn().mockResolvedValue(undefined);
        addEventListener = vi.fn((type: string, cb: (event?: any) => void) => {
          (this.listeners[type] ||= []).push(cb);
        });
        removeEventListener = vi.fn();
        getStats = vi.fn().mockResolvedValue(new Map());
        constructor(config?: any) {
          this.config = config;
        }
      },
      RTCDataChannel: {
        prototype: {
          send: nativeDataChannelSend,
        },
      },
    };
    fakeWindow.RTCPeerConnection.prototype.setConfiguration = nativeSetConfigurationSpy;
    fakeWindow.WebSocket.OPEN = 1;
  });

  it("rewrites signaling WebSocket URL to /stream/{profileId}/signal", () => {
    installSelkiesClientAdapter(fakeWindow, "prof_456");
    const ws = new fakeWindow.WebSocket("/api/webrtc/signaling");
    expect(ws.url).toBe("wss://cbrowser.local/stream/prof_456/signal");
  });

  it("AC-004: blocks activity frames and data channel resize commands at the real send boundary", () => {
    installSelkiesClientAdapter(fakeWindow, "prof_456");
    expect(fakeWindow.enable_resize).toBe(false);
    expect(fakeWindow.manual_resolution).toBe(true);

    const ws = new fakeWindow.WebSocket("/api/webrtc/signaling");

    // Activity frame must never reach the underlying WebSocket send.
    ws.send(JSON.stringify({ cbrowser: "activity", seq: 1 }));
    expect(ws.sent).toHaveLength(0);

    // Non-activity frames still pass through to the underlying send.
    ws.send("PING");
    expect(ws.sent).toEqual(["PING"]);

    // Resize packet must never reach the underlying RTCDataChannel send.
    fakeWindow.RTCDataChannel.prototype.send("r,1920,1080");
    expect(nativeDataChannelSend).not.toHaveBeenCalled();
    expect(fakeWindow.__sentDataChannelMessages).toEqual([]);

    // Non-resize packets still reach the data channel and are observable.
    fakeWindow.RTCDataChannel.prototype.send("k,abc");
    expect(nativeDataChannelSend).toHaveBeenCalledTimes(1);
    expect(nativeDataChannelSend).toHaveBeenCalledWith("k,abc");
    expect(fakeWindow.__sentDataChannelMessages).toEqual(["k,abc"]);
  });

  it("AC-002: appends noopener to window.open and to target=_blank links", () => {
    installSelkiesClientAdapter(fakeWindow, "prof_456");

    fakeWindow.open("https://example.com", "_blank");
    expect(openSpy).toHaveBeenCalledTimes(1);
    expect(String(openSpy.mock.calls[0][2])).toContain("noopener");

    const clickCall = fakeWindow.document.addEventListener.mock.calls.find(
      (call: any[]) => call[0] === "click"
    );
    expect(clickCall).toBeDefined();
    const handler = clickCall![1];

    const freshAnchor = {
      target: "_blank",
      getAttribute: vi.fn(() => ""),
      setAttribute: vi.fn(),
    };
    handler({ target: { closest: () => freshAnchor } });
    expect(freshAnchor.setAttribute).toHaveBeenCalledWith("rel", "noopener");

    const relAnchor = {
      target: "_blank",
      getAttribute: vi.fn(() => "nofollow"),
      setAttribute: vi.fn(),
    };
    handler({ target: { closest: () => relAnchor } });
    expect(relAnchor.setAttribute).toHaveBeenCalledWith("rel", "nofollow noopener");
  });

  it("AC-007: posts peer connection state to the parent with the concrete origin", () => {
    installSelkiesClientAdapter(fakeWindow, "prof_456");
    const pc = new fakeWindow.RTCPeerConnection();

    for (const listener of pc.listeners["iceconnectionstatechange"] || []) {
      listener();
    }

    expect(fakeWindow.parent.postMessage).toHaveBeenCalledWith(
      {
        type: "CBROWSER_PC_STATE",
        connectionState: "new",
        iceConnectionState: "new",
        signalingState: "stable",
      },
      "https://cbrowser.local"
    );
  });

  it("d022: maintains rtc_config iceServers and iceTransportPolicy on setConfiguration", () => {
    installSelkiesClientAdapter(fakeWindow, "prof_456");
    const pc = new fakeWindow.RTCPeerConnection();

    // Apply rtc_config
    const gatewayConfig = {
      iceServers: [{ urls: ["turn:127.0.0.1:3478"] }],
      iceTransportPolicy: "relay",
    };
    fakeWindow.__applyGatewayRtcConfig(gatewayConfig);

    // Call setConfiguration with empty config - must retain gateway config
    pc.setConfiguration({ bundlePolicy: "max-bundle" });
    expect(nativeSetConfigurationSpy).toHaveBeenCalledWith(expect.objectContaining({
      iceServers: [{ urls: ["turn:127.0.0.1:3478"] }],
      iceTransportPolicy: "relay",
      bundlePolicy: "max-bundle",
    }));
  });

  it("handles Web Locks tab conflict by generating new tab id without kicking existing tab", async () => {
    // Simulate lock unavailable (another tab holds it)
    fakeWindow.navigator.locks.request.mockImplementation((_name: string, _opts: any, cb: any) => {
      cb(null); // lock is null -> collision!
      return Promise.resolve();
    });

    fakeWindow.sessionStorage.setItem("selkies_tab_id", "tab-orig-999");
    installSelkiesClientAdapter(fakeWindow, "prof_456");

    const ws = new fakeWindow.WebSocket("/api/webrtc/signaling");
    ws.send("HELLO client {\"client_tab_id\":\"tab-orig-999\"}");

    await new Promise(r => setTimeout(r, 10));

    // When lock unavailable, must remap tab id and close with 1000
    expect(fakeWindow.sessionStorage.getItem("selkies_tab_id")).toBe("uuid-fixed-1234");
    expect(ws.close).toHaveBeenCalledWith(1000, "tab_collision_remap");
  });
});
