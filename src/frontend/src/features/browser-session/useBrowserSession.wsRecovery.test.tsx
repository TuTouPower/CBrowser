import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import React from "react";
import { useBrowserSession } from "./useBrowserSession";
import { I18nProvider } from "../../i18n";
import type { ApiClient } from "../../shared/api/client";
import type { SelkiesStats } from "./types";

// t061 AC-006: after an abnormal signaling WS close on a live session,
// the existing 5s recovery check re-reads WebRTC stats. When the media
// is still healthy the stage must leave "reconnecting" and return to
// "connected" WITHOUT rebuilding the iframe (reloadKey unchanged) —
// even when the ConnectionSnapshot never changed, so the diagnostics
// source emits no further connection signal.

type SessionOptions = NonNullable<Parameters<typeof useBrowserSession>[2]>;

function healthyStats(): SelkiesStats {
  return {
    video: {
      framesDecoded: 120,
      keyFramesDecoded: 4,
      bytesReceived: 8192,
      packetsLost: 0,
      packetsReceived: 200,
    },
    audio: null,
    pair: null,
    tab_id: "tab-1",
    connected: true,
    connectionState: "connected",
    iceConnectionState: "connected",
    signalingState: "stable",
  };
}

function setup(options: Partial<SessionOptions> = {}) {
  const getRuntime = vi.fn(async () => ({
    profile_id: "p1",
    display_number: 1,
    desired_state: "running",
    observed_state: "running",
  }));
  const apiClient = { profiles: { getRuntime } } as unknown as ApiClient;
  const iframe = document.createElement("iframe");
  document.body.appendChild(iframe);
  const ref = { current: iframe } as React.RefObject<HTMLIFrameElement | null>;
  const opts = {
    apiClient,
    initialStage: "connected",
    runtimeState: "running",
    ...options,
  } as SessionOptions;
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <I18nProvider>{children}</I18nProvider>
  );
  const rendered = renderHook(() => useBrowserSession("p1", ref, opts), {
    wrapper,
  });
  return { ...rendered, iframe, getRuntime };
}

function setStats(iframe: HTMLIFrameElement, impl: () => Promise<unknown>) {
  const frameWindow = iframe.contentWindow as unknown as {
    __getWebRTCStats: () => Promise<unknown>;
  };
  frameWindow.__getWebRTCStats = vi.fn(impl);
}

function dispatchWsClose(iframe: HTMLIFrameElement, code: number) {
  act(() => {
    window.dispatchEvent(
      new MessageEvent("message", {
        data: { type: "CBROWSER_WS_CLOSE", code },
        origin: window.location.origin,
        source: iframe.contentWindow,
      }),
    );
  });
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("useBrowserSession WS recovery check (t061 AC-006)", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("cbrowser.locale", "en");
    vi.restoreAllMocks();
    vi.useFakeTimers({
      toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date"],
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
    localStorage.clear();
  });

  it("healthy media + unchanged snapshot exits reconnecting to connected without a rebuild", async () => {
    const { result, iframe } = setup();
    setStats(iframe, async () => healthyStats());

    // Let the diagnostics source take its first sample: the snapshot
    // settles at healthy and never changes again after this point.
    await advance(1500);
    expect(result.current.stage).toBe("connected");

    dispatchWsClose(iframe, 1006);
    expect(result.current.stage).toBe("reconnecting");

    // The 5s recovery check fires; stats are still healthy and the
    // ConnectionSnapshot is unchanged, so no new connection signal
    // arrives — the check itself must end the recovery presentation.
    await advance(5000);
    expect(result.current.stage).toBe("connected");
    expect(result.current.reloadKey).toBe(0);
    expect(result.current.errorMessage).toBeNull();
  });

  it("unhealthy media at the recovery check falls back to the existing rebuild path", async () => {
    const { result, iframe } = setup();
    setStats(iframe, async () => ({
      ...healthyStats(),
      connected: false,
      connectionState: "disconnected",
      iceConnectionState: "disconnected",
    }));

    await advance(1500);
    dispatchWsClose(iframe, 1006);
    expect(result.current.stage).toBe("reconnecting");

    await advance(5000);
    expect(result.current.reloadKey).toBe(1);
    expect(result.current.stage).toBe("reconnecting");
  });

  it("a late healthy result from an old generation does not overwrite the current stage", async () => {
    const { result, iframe } = setup();
    let deferred: ((stats: SelkiesStats) => void) | null = null;
    let holdStats = false;
    setStats(iframe, () => {
      if (holdStats) {
        return new Promise<SelkiesStats>((resolve) => {
          deferred = resolve;
        });
      }
      return Promise.resolve(healthyStats());
    });

    await advance(1500);
    holdStats = true;
    dispatchWsClose(iframe, 1006);
    expect(result.current.stage).toBe("reconnecting");

    // Fire the 5s recovery check; its stats read stays in flight.
    await advance(5000);

    // A newer generation starts (manual reconnect) while the old
    // generation's check is still awaiting stats.
    act(() => {
      result.current.reconnect();
    });
    expect(result.current.reloadKey).toBe(1);

    // The stale check now resolves healthy: it must not connect the
    // new generation or clear its state.
    await act(async () => {
      deferred?.(healthyStats());
      await Promise.resolve();
    });
    expect(result.current.stage).toBe("reconnecting");
    expect(result.current.reloadKey).toBe(1);
  });

  it("a stopped backend ignores the abnormal close entirely (no recovery, no rebuild)", async () => {
    const { result, iframe } = setup({ runtimeState: "stopped" });
    setStats(iframe, async () => healthyStats());

    await advance(1500);
    dispatchWsClose(iframe, 1006);
    await advance(10000);

    expect(result.current.stage).toBe("connected");
    expect(result.current.reloadKey).toBe(0);
  });
});
