import { describe, it, expect, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { installSelkiesClientAdapter } from "./adapter";

const adapterSource = readFileSync(
  resolve(process.cwd(), "src/features/browser-session/adapter.ts"),
  "utf8"
);

class MockRTCPeerConnection {
  connectionState = "connected";
  iceConnectionState = "connected";
  signalingState = "stable";
  addEventListener = vi.fn();
  removeEventListener = vi.fn();
  getStats = vi.fn().mockResolvedValue(new Map<string, unknown>());
  constructor(public config?: RTCConfiguration) {}
}

function makeStatsWindow(): Record<string, unknown> {
  const win = {
    location: {
      href: "https://cbrowser.local/selkies/index.html?profileId=p1",
      search: "?profileId=p1",
      protocol: "https:",
      host: "cbrowser.local",
      origin: "https://cbrowser.local",
    },
    sessionStorage: {
      data: {} as Record<string, string>,
      getItem(k: string) {
        return this.data[k] ?? null;
      },
      setItem(k: string, v: string) {
        this.data[k] = v;
      },
    },
    crypto: { randomUUID: () => "uuid-fixed" },
    navigator: { locks: { request: vi.fn() } },
    document: { addEventListener: vi.fn(), removeEventListener: vi.fn() },
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    open: vi.fn(),
    parent: { postMessage: vi.fn() },
    frameElement: null,
    WebSocket: class {
      static OPEN = 1;
      readyState = 1;
      sent: string[] = [];
      send(data: string) {
        this.sent.push(data);
      }
      close = vi.fn();
      addEventListener = vi.fn();
      removeEventListener = vi.fn();
    },
    RTCPeerConnection: MockRTCPeerConnection,
    RTCDataChannel: { prototype: { send: vi.fn() } },
  };
  return win as unknown as Record<string, unknown>;
}

function installWithStats(
  entries: Array<[string, unknown]>
): Promise<unknown> {
  const win = makeStatsWindow();
  installSelkiesClientAdapter(win as unknown as Window, "p1");
  const pc = new (win.RTCPeerConnection as typeof MockRTCPeerConnection)();
  (pc.getStats as ReturnType<typeof vi.fn>).mockResolvedValue(new Map(entries));
  const read = (win as { __getWebRTCStats: () => Promise<unknown> })
    .__getWebRTCStats;
  return read();
}

describe("adapter.ts explicit any cleanup (A23)", () => {
  it("declares every boundary with a concrete type instead of any", () => {
    expect(adapterSource.match(/\bany\b/g) ?? []).toHaveLength(0);
  });
});

describe("adapter.ts RTCStats unknown-boundary runtime validation (A23)", () => {
  it("rejects non-numeric counters instead of forwarding raw values", async () => {
    const stats = (await installWithStats([
      [
        "v1",
        {
          id: "v1",
          type: "inbound-rtp",
          kind: "video",
          framesDecoded: "99",
          keyFramesDecoded: { n: 1 },
          bytesReceived: null,
          packetsLost: [],
          packetsReceived: 17,
        },
      ],
    ])) as { video: Record<string, unknown> };

    expect(stats.video.framesDecoded).toBe(0);
    expect(stats.video.keyFramesDecoded).toBe(0);
    expect(stats.video.bytesReceived).toBe(0);
    expect(stats.video.packetsLost).toBe(0);
    expect(stats.video.packetsReceived).toBe(17);
  });

  it("rejects malformed candidate-pair fields instead of forwarding raw values", async () => {
    const stats = (await installWithStats([
      [
        "pair1",
        {
          id: "pair1",
          type: "candidate-pair",
          selected: true,
          localCandidateId: "local1",
          remoteCandidateId: "remote1",
          bytesReceived: 42,
          currentRoundTripTime: "0.25",
        },
      ],
      ["local1", { id: "local1", candidateType: 7 }],
      [
        "remote1",
        {
          id: "remote1",
          candidateType: "srflx",
          ip: 203,
          address: 204,
          port: "443",
          usernameFragment: ["ufrag"],
        },
      ],
    ])) as { pair: Record<string, unknown> };

    expect(stats.pair.localType).toBeNull();
    expect(stats.pair.remoteType).toBe("srflx");
    expect(stats.pair.remoteAddress).toBeNull();
    expect(stats.pair.remotePort).toBeNull();
    expect(stats.pair.remoteUfrag).toBeNull();
    expect(stats.pair.roundTripTime).toBe(0);
    expect(stats.pair.bytesReceived).toBe(42);
  });

  it("ignores null report entries and still returns a well-shaped snapshot", async () => {
    const stats = (await installWithStats([["junk", null]])) as {
      video: unknown;
      audio: unknown;
      pair: unknown;
      connected: boolean;
    };

    expect(stats).not.toBeNull();
    expect(stats.video).toBeNull();
    expect(stats.audio).toBeNull();
    expect(stats.pair).toBeNull();
    expect(stats.connected).toBe(true);
  });

  it("keeps native constructor statics and prototype chain", () => {
    const win = makeStatsWindow();
    const Native = win.WebSocket as unknown as {
      OPEN: number;
      new (url: string): { readyState: number };
    };
    installSelkiesClientAdapter(win as unknown as Window, "p1");
    const Shim = win.WebSocket as unknown as {
      OPEN: number;
      new (url: string): { readyState: number };
    };

    expect(Shim.OPEN).toBe(Native.OPEN);
    expect(new Shim("wss://cbrowser.local/stream/p1/signal")).toBeInstanceOf(
      Native
    );
  });

  it("posts lifecycle stale on persisted pageshow and resume with a broken connection", () => {
    const win = makeStatsWindow();
    installSelkiesClientAdapter(win as unknown as Window, "p1");
    const pc = new (win.RTCPeerConnection as typeof MockRTCPeerConnection)();
    pc.connectionState = "failed";

    const addWindow = win.addEventListener as unknown as ReturnType<
      typeof vi.fn
    >;
    const addDocument = (
      win.document as unknown as { addEventListener: ReturnType<typeof vi.fn> }
    ).addEventListener;
    const pageshow = addWindow.mock.calls.find((call) => call[0] === "pageshow")?.[1] as
      | ((event: PageTransitionEvent) => void)
      | undefined;
    const resume = addDocument.mock.calls.find((call) => call[0] === "resume")?.[1] as
      | ((event: Event) => void)
      | undefined;

    expect(pageshow).toBeTypeOf("function");
    expect(resume).toBeTypeOf("function");
    const postMessage = (
      win.parent as unknown as { postMessage: ReturnType<typeof vi.fn> }
    ).postMessage;
    pageshow?.({ persisted: true } as PageTransitionEvent);
    expect(postMessage).toHaveBeenCalledWith(
      { type: "CBROWSER_LIFECYCLE_STALE" },
      "https://cbrowser.local"
    );
    resume?.(new Event("resume"));
    expect(postMessage).toHaveBeenCalledTimes(2);
  });
});
