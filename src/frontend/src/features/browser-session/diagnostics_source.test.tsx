import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render } from "@testing-library/react";
import { useSyncExternalStore } from "react";
import type { SelkiesStats } from "./types";
import {
  SessionDiagnosticsSource,
  type SessionDiagnosticsStoreSnapshot,
} from "./diagnostics_source";

class ControlledStats {
  calls = 0;
  private waits: Array<(value: SelkiesStats | null) => void> = [];

  read = (): Promise<SelkiesStats | null> => {
    this.calls += 1;
    return new Promise((resolve) => {
      this.waits.push(resolve);
    });
  };

  resolve(value: SelkiesStats | null): void {
    this.waits.shift()?.(value);
  }

  get inFlight(): number {
    return this.waits.length;
  }
}

function stats(partial: Partial<SelkiesStats> = {}): SelkiesStats {
  return {
    video: null,
    audio: null,
    pair: null,
    tab_id: null,
    connected: false,
    connectionState: "new",
    iceConnectionState: "new",
    signalingState: "stable",
    ...partial,
  };
}

function video(framesDecoded: number): SelkiesStats["video"] {
  return {
    framesDecoded,
    keyFramesDecoded: 1,
    bytesReceived: 100,
    packetsLost: 0,
    packetsReceived: 10,
  };
}

async function advance(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

async function flush(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function setHidden(hidden: boolean): void {
  Object.defineProperty(document, "hidden", {
    configurable: true,
    value: hidden,
  });
}

function makeSource(controlled: ControlledStats, intervalMs = 1000) {
  const onConnectionSignal = vi.fn();
  const source = new SessionDiagnosticsSource({
    readStats: controlled.read,
    onConnectionSignal,
    intervalMs,
  });
  return { source, onConnectionSignal };
}

beforeEach(() => {
  vi.useFakeTimers({
    toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"],
  });
  setHidden(false);
});

afterEach(() => {
  vi.useRealTimers();
  setHidden(false);
});

describe("SessionDiagnosticsSource sampling loop (A40)", () => {
  it("never overlaps a slow stats read and re-arms only after completion", async () => {
    const controlled = new ControlledStats();
    const { source } = makeSource(controlled);
    source.setActive(true);

    await advance(10);
    expect(controlled.calls).toBe(1);
    await advance(5000);
    expect(controlled.calls).toBe(1);

    controlled.resolve(stats({ video: video(4), connectionState: "connected" }));
    await flush();
    expect(controlled.inFlight).toBe(0);

    await advance(1000);
    expect(controlled.calls).toBe(2);
    await advance(5000);
    expect(controlled.calls).toBe(2);
  });

  it("shares one poller between multiple subscribers and unsubscribes cleanly", async () => {
    const controlled = new ControlledStats();
    const { source } = makeSource(controlled);
    const first = vi.fn();
    const second = vi.fn();
    const unsubscribeFirst = source.subscribe(first);
    source.subscribe(second);
    source.setActive(true);

    await advance(10);
    controlled.resolve(stats({ video: video(2), connectionState: "connected" }));
    await flush();

    expect(controlled.calls).toBe(1);
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);

    unsubscribeFirst();
    await advance(1000);
    controlled.resolve(stats({ video: video(3), connectionState: "connected" }));
    await flush();

    expect(controlled.calls).toBe(2);
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(2);
  });

  it("keeps snapshot identity stable when sampled values do not change", async () => {
    const controlled = new ControlledStats();
    const { source } = makeSource(controlled);
    const snapshotBefore = source.getSnapshot();
    const renders = vi.fn();

    function Leaf() {
      renders();
      const snapshot = useSyncExternalStore(source.subscribe, source.getSnapshot);
      return <span>{snapshot.diagnostics.framesDecoded ?? "-"}</span>;
    }

    render(<Leaf />);
    const initialRenders = renders.mock.calls.length;
    source.setActive(true);
    await advance(10);
    controlled.resolve(stats({ video: video(7), connectionState: "connected" }));
    await flush();
    expect(renders.mock.calls.length).toBe(initialRenders + 1);

    const firstUpdate = source.getSnapshot();
    await advance(1000);
    controlled.resolve(stats({ video: video(7), connectionState: "connected" }));
    await flush();

    expect(source.getSnapshot()).toBe(firstUpdate);
    expect(renders.mock.calls.length).toBe(initialRenders + 1);
    expect(snapshotBefore.connection).toBeDefined();
  });

  it("discards results from an older generation", async () => {
    const controlled = new ControlledStats();
    const { source, onConnectionSignal } = makeSource(controlled);
    source.setActive(true);

    await advance(10);
    expect(controlled.calls).toBe(1);
    source.setGeneration(2);
    controlled.resolve(stats({ video: video(99), connectionState: "connected" }));
    await flush();

    expect(source.getConnectionSnapshot().hasFrames).toBe(false);
    expect(onConnectionSignal).not.toHaveBeenCalled();

    await advance(10);
    expect(controlled.calls).toBe(2);
    controlled.resolve(stats({ video: video(3), connectionState: "connected" }));
    await flush();
    expect(source.getConnectionSnapshot().hasFrames).toBe(true);
    expect(source.getDiagnosticsSnapshot().framesDecoded).toBe(3);
  });

  it("stops sampling on terminal/deactivation and clears in-flight work", async () => {
    const controlled = new ControlledStats();
    const { source } = makeSource(controlled);
    source.setActive(true);
    await advance(10);
    expect(controlled.calls).toBe(1);

    source.setActive(false);
    controlled.resolve(stats({ video: video(5) }));
    await flush();
    await advance(5000);
    expect(controlled.calls).toBe(1);
    expect(source.getConnectionSnapshot()).toEqual({
      connected: false,
      hasFrames: false,
      connectionState: null,
      iceConnectionState: null,
      signalingState: null,
    });

    source.dispose();
    expect(source.getSnapshot().connection.connected).toBe(false);
  });

  it("keeps connection facts while high-frequency publishing is disabled", async () => {
    const controlled = new ControlledStats();
    const { source, onConnectionSignal } = makeSource(controlled);
    source.setDiagnosticsEnabled(false);
    source.setActive(true);

    await advance(10);
    controlled.resolve(stats({ video: video(8), connectionState: "connected" }));
    await flush();
    expect(onConnectionSignal).toHaveBeenCalledTimes(1);
    expect(source.getConnectionSnapshot().hasFrames).toBe(true);
    expect(source.getDiagnosticsSnapshot().framesDecoded).toBeUndefined();

    await advance(1000);
    controlled.resolve(stats({ video: video(20), connectionState: "connected" }));
    await flush();
    expect(source.getConnectionSnapshot().hasFrames).toBe(true);
    expect(source.getDiagnosticsSnapshot().framesDecoded).toBeUndefined();

    source.setDiagnosticsEnabled(true);
    await advance(1000);
    controlled.resolve(stats({ video: video(20), connectionState: "connected" }));
    await flush();
    expect(source.getDiagnosticsSnapshot().framesDecoded).toBe(20);
  });

  it("keeps connection facts but freezes diagnostics while document is hidden", async () => {
    const controlled = new ControlledStats();
    const { source } = makeSource(controlled);
    setHidden(true);
    source.setActive(true);

    await advance(10);
    controlled.resolve(stats({ video: video(11), connectionState: "connected" }));
    await flush();
    expect(source.getConnectionSnapshot().connectionState).toBe("connected");
    expect(source.getDiagnosticsSnapshot().framesDecoded).toBeUndefined();
  });

  it("publishes formatted diagnostics values from a valid stats sample", async () => {
    const controlled = new ControlledStats();
    const { source } = makeSource(controlled);
    source.setActive(true);

    await advance(10);
    controlled.resolve(
      stats({
        connected: true,
        connectionState: "connected",
        iceConnectionState: "connected",
        signalingState: "stable",
        video: {
          framesDecoded: 42,
          keyFramesDecoded: 2,
          bytesReceived: 1000,
          packetsLost: 3,
          packetsReceived: 500,
        },
        pair: {
          localType: "host",
          remoteType: "srflx",
          remoteAddress: "127.0.0.1",
          remotePort: 443,
          remoteUfrag: "ufrag",
          roundTripTime: 0.025,
          bytesReceived: 1000,
        },
        audio: {
          totalAudioEnergy: 1,
          bytesReceived: 10,
          packetsReceived: 5,
          packetsLost: 0,
          trackIdentifier: "audio-1",
        },
      })
    );
    await flush();

    const diagnostics = source.getDiagnosticsSnapshot();
    expect(diagnostics.framesDecoded).toBe(42);
    expect(diagnostics.roundTripTime).toBe(25);
    expect(diagnostics.packetsLost).toBe(3);
    expect(diagnostics.packetsReceived).toBe(500);
    expect(diagnostics.audioStatus).toBeDefined();
    const store: SessionDiagnosticsStoreSnapshot = source.getSnapshot();
    expect(store.connection.connected).toBe(true);
    expect(store.diagnostics).toBe(diagnostics);
  });

  it("publishes the selected candidate pair and keeps identity stable while it is unchanged", async () => {
    const controlled = new ControlledStats();
    const { source } = makeSource(controlled);
    source.setActive(true);

    await advance(10);
    controlled.resolve(
      stats({
        connected: true,
        connectionState: "connected",
        video: video(9),
        pair: {
          localType: "host",
          remoteType: "srflx",
          remoteAddress: "127.0.0.1",
          remotePort: 443,
          remoteUfrag: "ufrag",
          roundTripTime: 0.025,
          bytesReceived: 100,
        },
      })
    );
    await flush();
    const first = source.getSnapshot();
    expect(first.diagnostics.selectedPair?.localType).toBe("host");
    expect(first.diagnostics.selectedPair?.remoteType).toBe("srflx");
    expect(first.diagnostics.selectedPair?.remoteAddress).toBe("127.0.0.1");
    expect(first.diagnostics.selectedPair?.remotePort).toBe(443);

    await advance(1000);
    controlled.resolve(
      stats({
        connected: true,
        connectionState: "connected",
        video: video(9),
        pair: {
          localType: "host",
          remoteType: "srflx",
          remoteAddress: "127.0.0.1",
          remotePort: 443,
          remoteUfrag: "ufrag",
          roundTripTime: 0.025,
          bytesReceived: 100,
        },
      })
    );
    await flush();
    expect(source.getSnapshot()).toBe(first);
  });

  it("getSnapshot and subscribe keep stable identities", () => {
    const { source } = makeSource(new ControlledStats());
    expect(source.getSnapshot()).toBe(source.getSnapshot());
    expect(source.subscribe).toBe(source.subscribe);
    expect(source.getSnapshot).toBe(source.getSnapshot);
  });
});
