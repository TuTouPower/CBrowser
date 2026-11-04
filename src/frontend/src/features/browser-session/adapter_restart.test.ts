import { describe, it, expect, vi } from "vitest";
import { installSelkiesClientAdapter } from "./adapter";

class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  readyState = MockWebSocket.OPEN;
  sent: string[] = [];
  handlers = new Map<string, Array<(event: any) => any>>();

  constructor(public url: string) {}

  send = (data: any) => {
    this.sent.push(data);
  };

  close = vi.fn();

  addEventListener(type: string, listener: (event: any) => any) {
    const list = this.handlers.get(type) || [];
    list.push(listener);
    this.handlers.set(type, list);
  }

  removeEventListener() {}
}

class MockRTCPeerConnection {
  connectionState = "connected";
  iceConnectionState = "connected";
  signalingState = "stable";
  addEventListener = vi.fn();
  removeEventListener = vi.fn();
  getStats = vi.fn().mockResolvedValue(new Map());
  constructor(public config?: any) {}
}

function makeWindow(): any {
  const win: any = {
    location: {
      href: "https://cbrowser.local/selkies/index.html?profileId=prof_456",
      search: "?profileId=prof_456",
      protocol: "https:",
      host: "cbrowser.local",
      origin: "https://cbrowser.local",
    },
    sessionStorage: {
      data: {} as Record<string, string>,
      getItem(k: string) {
        return this.data[k] || null;
      },
      setItem(k: string, v: string) {
        this.data[k] = v;
      },
    },
    crypto: { randomUUID: () => "uuid-fixed-1234" },
    navigator: { locks: { request: vi.fn() } },
    document: { addEventListener: vi.fn(), removeEventListener: vi.fn() },
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    open: vi.fn(),
    parent: { postMessage: vi.fn() },
    WebSocket: MockWebSocket as any,
    RTCPeerConnection: MockRTCPeerConnection as any,
    RTCDataChannel: { prototype: { send: vi.fn() } },
  };
  return win;
}

describe("SelkiesClientAdapter production contract", () => {
  it("rewrites signaling to the profile stream route", () => {
    const win = makeWindow();
    installSelkiesClientAdapter(win, "prof_456");
    const ws = new win.WebSocket("/api/webrtc/signaling");
    expect(ws.url).toBe("wss://cbrowser.local/stream/prof_456/signal");
  });

  it("does not expose test hooks on the iframe window", () => {
    const win = makeWindow();
    installSelkiesClientAdapter(win, "prof_456");
    for (const name of [
      "__sentDataChannelMessages",
      "__pcs",
      "__inputChannel",
      "__last_ws",
      "__latestRtcConfig",
      "__restartOffers",
      "__activePC",
      "__NativeWebSocket",
      "__NativeRTCPeerConnection",
      "__cbrowserShimInstalled",
    ]) {
      expect(win[name]).toBeUndefined();
    }
    expect(typeof win.__getWebRTCStats).toBe("function");
  });

  it("strips Selkies default external STUN for the ICE-lite media path", () => {
    const win = makeWindow();
    installSelkiesClientAdapter(win, "prof_456");
    const pc = new win.RTCPeerConnection({
      iceServers: [{ urls: ["stun:stun.l.google.com:19302"] }],
      iceTransportPolicy: "all",
    });
    expect(pc.config.iceServers).toEqual([]);
    expect(pc.config.iceTransportPolicy).toBe("all");
  });

  it("blocks client resize packets at the data channel boundary", () => {
    const win = makeWindow();
    const nativeSend = vi.fn();
    win.RTCDataChannel = { prototype: { send: nativeSend } };
    installSelkiesClientAdapter(win, "prof_456");
    win.RTCDataChannel.prototype.send("r,1920,1080");
    expect(nativeSend).not.toHaveBeenCalled();
    win.RTCDataChannel.prototype.send("k,abc");
    expect(nativeSend).toHaveBeenCalledWith("k,abc");
  });

  it("reports unavailable Web Locks as a dedicated parent message", async () => {
    const win = makeWindow();
    win.navigator.locks.request.mockRejectedValue(new Error("no locks"));
    installSelkiesClientAdapter(win, "prof_456");
    const ws = new win.WebSocket("/api/webrtc/signaling");
    ws.send('HELLO client {"client_tab_id":"tab-1"}');
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(win.parent.postMessage).toHaveBeenCalledWith(
      { type: "CBROWSER_WEB_LOCKS_UNAVAILABLE" },
      "https://cbrowser.local"
    );
    expect(ws.close).toHaveBeenCalledWith(1008, "tab_identity_unavailable");
  });

  it("posts WebSocket close events to the parent", () => {
    const win = makeWindow();
    installSelkiesClientAdapter(win, "prof_456");
    const ws = new win.WebSocket("/api/webrtc/signaling");
    for (const handler of ws.handlers.get("close") || []) {
      handler({ code: 1006, reason: "lost" });
    }
    expect(win.parent.postMessage).toHaveBeenCalledWith(
      { type: "CBROWSER_WS_CLOSE", code: 1006, reason: "lost" },
      "https://cbrowser.local"
    );
  });

  it("returns session statistics through the documented host contract", async () => {
    const win = makeWindow();
    installSelkiesClientAdapter(win, "prof_456");
    const pc = new win.RTCPeerConnection();
    pc.getStats.mockResolvedValue(
      new Map([
        [
          "v1",
          { id: "v1", type: "inbound-rtp", kind: "video", framesDecoded: 12 },
        ],
      ])
    );
    const stats = await win.__getWebRTCStats();
    expect(stats.video.framesDecoded).toBe(12);
    expect(stats.connected).toBe(true);
    expect(stats.tab_id).toBeNull();
  });

  it("guards keyboard events when iframe does not have active focus", () => {
    const win = makeWindow();
    const listeners = new Map<string, Array<(event: any) => void>>();
    win.addEventListener = vi.fn((type: string, fn: any) => {
      const list = listeners.get(type) || [];
      list.push(fn);
      listeners.set(type, list);
    });

    // Case 1: hasFocus is false
    win.document.hasFocus = vi.fn(() => false);
    installSelkiesClientAdapter(win, "prof_456");

    expect(listeners.has("keydown")).toBe(true);
    const keydownHandler = listeners.get("keydown")?.[0];
    if (!keydownHandler) {
      throw new Error("keydownHandler not found");
    }

    const unfocusedEvent = {
      type: "keydown",
      key: "r",
      metaKey: true,
      shiftKey: true,
      stopImmediatePropagation: vi.fn(),
    };
    keydownHandler(unfocusedEvent);
    expect(unfocusedEvent.stopImmediatePropagation).toHaveBeenCalled();

    // Case 2: parent activeElement is not this frame
    const frameEl = {};
    win.frameElement = frameEl;
    win.parent.document = { activeElement: {} }; // not frameEl
    win.document.hasFocus = vi.fn(() => true);

    const unfocusedParentEvent = {
      type: "keydown",
      key: "r",
      metaKey: true,
      shiftKey: true,
      stopImmediatePropagation: vi.fn(),
    };
    keydownHandler(unfocusedParentEvent);
    expect(unfocusedParentEvent.stopImmediatePropagation).toHaveBeenCalled();

    // Case 3: frame has active focus
    win.parent.document.activeElement = frameEl;
    const focusedEvent = {
      type: "keydown",
      key: "r",
      metaKey: true,
      shiftKey: true,
      stopImmediatePropagation: vi.fn(),
    };
    keydownHandler(focusedEvent);
    expect(focusedEvent.stopImmediatePropagation).not.toHaveBeenCalled();
  });
});
