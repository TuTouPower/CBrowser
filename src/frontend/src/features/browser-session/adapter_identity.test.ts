import { describe, it, expect, vi } from "vitest";
import { installSelkiesClientAdapter } from "./adapter";
import { resolveSelkiesProfileId } from "./selkies_profile_id";

// t069 strict viewer identity: the install-time profileId is the only
// identity source. Missing ids and global __CBROWSER_PROFILE_ID__
// injection are rejected, and the WebSocket shim never re-reads query
// parameters (profileId/profile_id) as identity.

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

function makeWindow(search = "?profileId=prof_456"): any {
  const win: any = {
    location: {
      href: `https://cbrowser.local/selkies/index.html${search}`,
      search,
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

describe("SelkiesClientAdapter strict identity (t069)", () => {
  it("rejects installation without a profileId", () => {
    const win = makeWindow();
    expect(() => installSelkiesClientAdapter(win, "")).toThrow(
      /non-empty profileId/
    );
    expect(() =>
      installSelkiesClientAdapter(win, undefined as unknown as string)
    ).toThrow(/non-empty profileId/);
  });

  it("rejects a __CBROWSER_PROFILE_ID__ global injection", () => {
    const win = makeWindow();
    win.__CBROWSER_PROFILE_ID__ = "prof_attacker";
    expect(() => installSelkiesClientAdapter(win, "prof_456")).toThrow(
      /__CBROWSER_PROFILE_ID__/
    );
  });

  it("shim uses only the install-time id, ignoring URL identity params", () => {
    const win = makeWindow("?profileId=prof_other&profile_id=prof_attacker");
    installSelkiesClientAdapter(win, "prof_456");
    const ws = new win.WebSocket("/api/webrtc/signaling");
    expect(ws.url).toBe("wss://cbrowser.local/stream/prof_456/signal");
  });
});

describe("selkies entry identity resolution (t069)", () => {
  it("accepts the documented profileId channel", () => {
    expect(resolveSelkiesProfileId("?profileId=prof_456")).toBe("prof_456");
  });

  it("rejects the undocumented profile_id parameter, even beside profileId", () => {
    expect(() => resolveSelkiesProfileId("?profile_id=prof_456")).toThrow(
      /profile_id/
    );
    expect(() =>
      resolveSelkiesProfileId("?profileId=prof_456&profile_id=prof_other")
    ).toThrow(/profile_id/);
  });

  it("rejects a missing or empty profileId instead of a default", () => {
    expect(() => resolveSelkiesProfileId("")).toThrow(/profileId/);
    expect(() => resolveSelkiesProfileId("?profileId=")).toThrow(/profileId/);
    expect(() => resolveSelkiesProfileId("?other=1")).toThrow(/profileId/);
  });
});
