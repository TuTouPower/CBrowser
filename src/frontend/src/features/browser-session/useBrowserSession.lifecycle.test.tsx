import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import React from "react";
import { useBrowserSession } from "./useBrowserSession";
import { I18nProvider } from "../../i18n";
import type { ApiClient } from "../../shared/api/client";

type SessionOptions = NonNullable<Parameters<typeof useBrowserSession>[2]>;
type StatsWindow = Window & {
  __getWebRTCStats?: () => Promise<{ connected: boolean } | null>;
};

function makeMessage(
  iframe: HTMLIFrameElement,
  data: Record<string, unknown>
): MessageEvent {
  return new MessageEvent("message", {
    data,
    origin: window.location.origin,
    source: iframe.contentWindow,
  });
}

function dispatch(iframe: HTMLIFrameElement, data: Record<string, unknown>): void {
  act(() => {
    window.dispatchEvent(makeMessage(iframe, data));
  });
}

function runtimeResponse(transportState?: string) {
  return {
    profile_id: "p1",
    display_number: 1,
    desired_state: "running",
    observed_state: "running",
    transport: transportState
      ? {
          profile_id: "p1",
          runtime_instance_id: "inst_1",
          browser_state: "running",
          stream_state: "running",
          transport_state: transportState,
        }
      : null,
  };
}

function setup(options: Partial<SessionOptions> = {}) {
  const getRuntime = vi.fn(async () => runtimeResponse());
  const apiClient = { profiles: { getRuntime } } as unknown as ApiClient;
  const iframe = document.createElement("iframe");
  document.body.appendChild(iframe);
  const ref = { current: iframe } as React.RefObject<HTMLIFrameElement | null>;
  const statsWindow = iframe.contentWindow as StatsWindow;
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <I18nProvider>{children}</I18nProvider>
  );
  const rendered = renderHook(
    ({ profileId, opts }) => useBrowserSession(profileId, ref, opts),
    {
      wrapper,
      initialProps: {
        profileId: "p1",
        opts: { apiClient, ...options } as SessionOptions,
      },
    }
  );
  return { ...rendered, iframe, statsWindow, getRuntime };
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("cbrowser.locale", "en");
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
  localStorage.clear();
});

describe("useBrowserSession unified runtime, generation fence, cleanup (A20)", () => {
  it("exposes a stable generation that increments on profileId and reloadKey changes", () => {
    const { result, rerender } = setup({ initialStage: "connected" });

    expect(typeof result.current.generation).toBe("number");
    const initial = result.current.generation;
    rerender({ profileId: "p2", opts: { initialStage: "connected" } as SessionOptions });
    expect(result.current.generation).toBeGreaterThan(initial);
    const afterProfile = result.current.generation;

    act(() => result.current.reconnect());
    expect(result.current.generation).toBeGreaterThan(afterProfile);
  });

  it("terminal runtime input stops stats sampling and connection recovery", async () => {
    vi.useFakeTimers();
    const { result, iframe, statsWindow, getRuntime } = setup({
      initialStage: "connected",
      runtimeState: "stopping",
    });
    const readStats = vi.fn(async () => ({ connected: true }));
    statsWindow.__getWebRTCStats = readStats;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(readStats).not.toHaveBeenCalled();

    dispatch(iframe, { type: "CBROWSER_WS_CLOSE", code: 1006 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(getRuntime).not.toHaveBeenCalled();
    expect(result.current.reloadKey).toBe(0);
  });

  it("clears the transport recovery timer and fences its poll on unmount", async () => {
    vi.useFakeTimers();
    const getRuntime = vi.fn(async () => runtimeResponse("recovering"));
    const apiClient = { profiles: { getRuntime } } as unknown as ApiClient;
    const iframe = document.createElement("iframe");
    document.body.appendChild(iframe);
    const ref = { current: iframe } as React.RefObject<HTMLIFrameElement | null>;
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <I18nProvider>{children}</I18nProvider>
    );
    const { unmount } = renderHook(
      () =>
        useBrowserSession("p1", ref, {
          apiClient,
          initialStage: "connecting_signaling",
          // t058 A39: recovery only starts once the first runtime check
          // has settled; without a runtime input the WS_CLOSE is recorded
          // and no poll starts.
          runtimeState: "running",
          transportRecoveryWindowMs: 60000,
        }),
      { wrapper }
    );

    dispatch(iframe, { type: "CBROWSER_WS_CLOSE", code: 1006 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const before = getRuntime.mock.calls.length;
    expect(before).toBeGreaterThan(0);

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(getRuntime.mock.calls.length).toBe(before);
  });

  it("discards a stale generation health-check result instead of reconnecting twice", async () => {
    vi.useFakeTimers();
    const { result, iframe, statsWindow } = setup({ initialStage: "connected" });
    let resolveStats: ((value: { connected: boolean }) => void) | undefined;
    statsWindow.__getWebRTCStats = () =>
      new Promise((resolve) => {
        resolveStats = resolve;
      });

    dispatch(iframe, { type: "CBROWSER_WS_CLOSE", code: 1006 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(resolveStats).toBeDefined();

    act(() => result.current.reconnect());
    expect(result.current.reloadKey).toBe(1);

    await act(async () => {
      resolveStats?.({ connected: false });
    });
    expect(result.current.reloadKey).toBe(1);
  });

  it("never starts a periodic runtime poll and leaves no timers after unmount", async () => {
    vi.useFakeTimers();
    const { unmount, getRuntime } = setup({ initialStage: "connected" });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(getRuntime).not.toHaveBeenCalled();

    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(vi.getTimerCount()).toBe(0);
    expect(getRuntime).not.toHaveBeenCalled();
  });

  // t058 A25 deleted the one-shot mount bootstrap ("only the one-shot
  // mount bootstrap touches getRuntime"): the hook no longer reads runtime
  // at all. The replacement — the hook never calls getRuntime for
  // stage/error — is covered by useBrowserSession.t058.test.tsx (AC-004).

  it("runtimeState is the single runtime-driven stage source, with no runtime poll", async () => {
    vi.useFakeTimers();
    const { result, rerender, getRuntime, statsWindow } = setup({
      initialStage: "connected",
    });
    const readStats = vi.fn(async () => ({ connected: true }));
    statsWindow.__getWebRTCStats = readStats;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(readStats).toHaveBeenCalled();
    readStats.mockClear();

    rerender({
      profileId: "p1",
      opts: {
        initialStage: "connected",
        runtimeState: "stopping",
      } as SessionOptions,
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });

    expect(getRuntime).not.toHaveBeenCalled();
    expect(readStats).not.toHaveBeenCalled();
    expect(result.current.stage).toBe("connected");
    expect(vi.getTimerCount()).toBe(0);
  });
});
