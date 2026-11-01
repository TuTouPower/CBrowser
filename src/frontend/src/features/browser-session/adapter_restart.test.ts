import { describe, it, expect, vi } from "vitest";
import {
  DATA_CHANNEL_HISTORY_LIMIT,
  RESTART_OFFER_HISTORY_LIMIT,
  installSelkiesClientAdapter,
} from "./adapter";

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
  iceGatheringState = "complete";
  localDescription = { type: "answer", sdp: "v=0\r\n" };
  setRemoteDescription = vi.fn().mockResolvedValue(undefined);
  createAnswer = vi.fn().mockResolvedValue({ type: "answer", sdp: "v=0\r\n" });
  setLocalDescription = vi.fn().mockResolvedValue(undefined);
  addEventListener = vi.fn();
  removeEventListener = vi.fn();
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
  win.RTCPeerConnection.prototype.setConfiguration = vi.fn();
  return win;
}

describe("SelkiesClientAdapter ice_restart parity", () => {
  it("records the restart offer ufrag and answers the Gateway generation", async () => {
    const win = makeWindow();
    installSelkiesClientAdapter(win, "prof_456");
    new win.RTCPeerConnection();

    const ws = new win.WebSocket("/api/webrtc/signaling");
    const handlers = (ws as any).handlers.get("message") || [];
    expect(handlers.length).toBeGreaterThan(0);

    const offer = {
      type: "offer",
      sdp: "v=0\r\na=ice-ufrag:UFRAG123\r\na=ice-pwd:secret\r\n",
    };
    await handlers[0]({
      data: JSON.stringify({
        cbrowser: "ice_restart",
        generation: 3,
        rtc_config: { iceServers: [{ urls: ["turn:127.0.0.1:3478"] }] },
        offer,
      }),
    });

    expect(win.__restartOffers).toEqual([
      { generation: 3, ufrag: "UFRAG123", offer },
    ]);
    expect(win.__latestRtcConfig).toEqual({
      iceServers: [{ urls: ["turn:127.0.0.1:3478"] }],
    });
    expect((ws as any).sent.length).toBe(1);
    expect(JSON.parse((ws as any).sent[0])).toMatchObject({
      cbrowser: "ice_restart_answer",
      generation: 3,
    });
  });
});

describe("SelkiesClientAdapter bounded diagnostics", () => {
  it("keeps the sent DataChannel history bounded", () => {
    const win = makeWindow();
    installSelkiesClientAdapter(win, "prof_456");

    const total = DATA_CHANNEL_HISTORY_LIMIT + 25;
    for (let i = 0; i < total; i += 1) {
      win.RTCDataChannel.prototype.send(`k,${i}`);
    }

    expect(win.__sentDataChannelMessages).toHaveLength(
      DATA_CHANNEL_HISTORY_LIMIT
    );
    expect(win.__sentDataChannelMessages[0]).toBe(
      `k,${total - DATA_CHANNEL_HISTORY_LIMIT}`
    );
    expect(win.__sentDataChannelMessages.at(-1)).toBe(`k,${total - 1}`);
  });

  it("retains only the active peer connection", () => {
    const win = makeWindow();
    installSelkiesClientAdapter(win, "prof_456");

    const first = new win.RTCPeerConnection();
    const second = new win.RTCPeerConnection();

    expect(win.__pcs).toHaveLength(1);
    expect(win.__pcs[0]).toBe(second);
    expect(win.__activePC).toBe(second);
    expect(win.__pcs).not.toContain(first);
  });

  it("caps recorded ICE restart offers", async () => {
    const win = makeWindow();
    installSelkiesClientAdapter(win, "prof_456");
    new win.RTCPeerConnection();

    const ws = new win.WebSocket("/api/webrtc/signaling");
    const handler = ((ws as any).handlers.get("message") || [])[0];
    const total = RESTART_OFFER_HISTORY_LIMIT + 5;
    for (let generation = 1; generation <= total; generation += 1) {
      await handler({
        data: JSON.stringify({
          cbrowser: "ice_restart",
          generation,
          offer: { type: "offer", sdp: "v=0\r\n" },
        }),
      });
    }

    expect(win.__restartOffers).toHaveLength(RESTART_OFFER_HISTORY_LIMIT);
    expect(win.__restartOffers[0].generation).toBe(
      total - RESTART_OFFER_HISTORY_LIMIT + 1
    );
    expect(win.__restartOffers.at(-1).generation).toBe(total);
  });
});
