import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import React from "react";
import { useBrowserSession } from "./useBrowserSession";
import { I18nProvider } from "../../i18n";
import { ApiClient } from "../../shared/api/client";

type SessionOptions = NonNullable<Parameters<typeof useBrowserSession>[2]>;
type MessageOverrides = { origin?: string; source?: MessageEventSource | null };

function makeMessage(
  iframe: HTMLIFrameElement,
  data: Record<string, unknown>,
  overrides: MessageOverrides = {}
): MessageEvent {
  const source =
    overrides.source === undefined
      ? (iframe.contentWindow as unknown as MessageEventSource | null)
      : overrides.source;
  return new MessageEvent("message", {
    data,
    origin: overrides.origin ?? window.location.origin,
    source,
  });
}

function dispatch(
  iframe: HTMLIFrameElement,
  data: Record<string, unknown>,
  overrides: MessageOverrides = {}
): void {
  act(() => {
    window.dispatchEvent(makeMessage(iframe, data, overrides));
  });
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
  const opts = { apiClient, ...options } as SessionOptions;
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <I18nProvider>{children}</I18nProvider>
  );
  const rendered = renderHook(() => useBrowserSession("p1", ref, opts), {
    wrapper,
  });
  return { ...rendered, iframe, getRuntime };
}

function useControlledTimers(): void {
  vi.useFakeTimers({
    toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date"],
  });
}

describe("useBrowserSession stage logic (deleted BrowserSessionView layer)", () => {
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

  it("1. unmount clears timers and blanks the iframe without stop/desired-state calls", () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}", { status: 200 }));
    const clearIntervalSpy = vi.spyOn(globalThis, "clearInterval");
    const { unmount, iframe } = setup({ initialStage: "connected" });

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
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(clearIntervalSpy).toHaveBeenCalled();
    expect(iframe.getAttribute("src")).toBe("about:blank");
  });

  // t058 A25 deleted test 2 ("a 401 is delegated to the auth layer"):
  // the hook no longer reads runtime, so there is no hook-side 401 to
  // delegate. The 401 path now belongs to the runtimeQuery in
  // SessionPage (its unauthorized flow redirects to login); the hook
  // contract that replaced it — no hook-side runtime read — is covered
  // by useBrowserSession.t058.test.tsx (AC-004).

  it("3. unmount releases message and lifecycle listeners", () => {
    const removeWindow = vi.spyOn(window, "removeEventListener");
    const removeDocument = vi.spyOn(document, "removeEventListener");
    const { unmount } = setup({ initialStage: "connected" });

    unmount();

    expect(removeWindow).toHaveBeenCalledWith("message", expect.any(Function));
    expect(removeWindow).toHaveBeenCalledWith("pageshow", expect.any(Function));
    expect(removeDocument).toHaveBeenCalledWith("resume", expect.any(Function));
  });

  it("4. a deferred WS close on a diagnostic stage does not migrate the stage", () => {
    const { result, iframe } = setup({ initialStage: "runtime_not_ready" });

    dispatch(iframe, {
      type: "CBROWSER_WS_CLOSE",
      code: 1006,
      reason: "profile_not_found",
    });

    expect(result.current.stage).toBe("runtime_not_ready");
    expect(result.current.reloadKey).toBe(0);
  });

  it("5. reconnect increments reloadKey and moves to reconnecting", () => {
    const { result } = setup({ initialStage: "ice_failed" });
    expect(result.current.reloadKey).toBe(0);

    act(() => {
      result.current.reconnect();
    });

    expect(result.current.reloadKey).toBe(1);
    expect(result.current.stage).toBe("reconnecting");
  });

  it("6. CBROWSER_PC_STATE failed migrates stage and diagnostics", () => {
    const { result, iframe } = setup({ initialStage: "media_waiting" });

    dispatch(iframe, {
      type: "CBROWSER_PC_STATE",
      connectionState: "failed",
      iceConnectionState: "failed",
      signalingState: "stable",
    });

    expect(result.current.stage).toBe("ice_failed");
    expect(result.current.diagnostics.iceConnectionState).toBe("failed");
    expect(result.current.diagnostics.connectionState).toBe("failed");
    expect(result.current.errorMessage).toBeTruthy();
  });

  it("7. a transient ICE disconnect recovering within the grace window is not a failure", () => {
    useControlledTimers();
    const { result, iframe } = setup({
      initialStage: "connected",
      iceDisconnectGraceMs: 5000,
    });

    act(() => {
      window.dispatchEvent(
        makeMessage(iframe, {
          type: "CBROWSER_PC_STATE",
          connectionState: "disconnected",
          iceConnectionState: "disconnected",
          signalingState: "stable",
        })
      );
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.stage).not.toBe("ice_failed");

    act(() => {
      window.dispatchEvent(
        makeMessage(iframe, {
          type: "CBROWSER_PC_STATE",
          connectionState: "connected",
          iceConnectionState: "connected",
          signalingState: "stable",
        })
      );
      vi.advanceTimersByTime(6000);
    });
    expect(result.current.stage).not.toBe("ice_failed");
  });

  it("8. a persistent ICE disconnect becomes ice_failed", () => {
    useControlledTimers();
    const { result, iframe } = setup({
      initialStage: "connected",
      iceDisconnectGraceMs: 5000,
    });

    act(() => {
      window.dispatchEvent(
        makeMessage(iframe, {
          type: "CBROWSER_PC_STATE",
          connectionState: "disconnected",
          iceConnectionState: "disconnected",
          signalingState: "stable",
        })
      );
      vi.advanceTimersByTime(5000);
    });

    expect(result.current.stage).toBe("ice_failed");
    expect(result.current.diagnostics.iceConnectionState).toBe("disconnected");
    expect(result.current.errorMessage).toBeTruthy();
  });

  it("9. CBROWSER_WS_CLOSE on a live connection rebuilds (reloadKey changes)", () => {
    useControlledTimers();
    const { result, iframe } = setup({ initialStage: "connected" });

    act(() => {
      window.dispatchEvent(
        makeMessage(iframe, {
          type: "CBROWSER_WS_CLOSE",
          code: 1006,
          reason: "abnormal",
        })
      );
      vi.advanceTimersByTime(5000);
    });

    expect(result.current.reloadKey).toBe(1);
    expect(result.current.stage).toBe("reconnecting");
  });

  it("10. CBROWSER_LIFECYCLE_STALE rebuilds and migrates the stage", () => {
    const { result, iframe } = setup({ initialStage: "connected" });

    dispatch(iframe, { type: "CBROWSER_LIFECYCLE_STALE" });

    expect(result.current.reloadKey).toBe(1);
    expect(result.current.stage).toBe("reconnecting");
  });

  it("11. bfcache pageshow(persisted) rebuilds only a dead connection", async () => {
    const { result, iframe } = setup({ initialStage: "connected" });
    const frameWindow = iframe.contentWindow as unknown as {
      __getWebRTCStats: () => Promise<{ connected: boolean }>;
    };

    frameWindow.__getWebRTCStats = vi.fn(async () => ({ connected: true }));
    await act(async () => {
      window.dispatchEvent(
        new PageTransitionEvent("pageshow", { persisted: true })
      );
    });
    expect(result.current.reloadKey).toBe(0);

    frameWindow.__getWebRTCStats = vi.fn(async () => ({ connected: false }));
    await act(async () => {
      window.dispatchEvent(
        new PageTransitionEvent("pageshow", { persisted: false })
      );
    });
    expect(result.current.reloadKey).toBe(0);

    await act(async () => {
      window.dispatchEvent(
        new PageTransitionEvent("pageshow", { persisted: true })
      );
    });
    expect(result.current.reloadKey).toBe(1);
  });

  it("12. forged source/origin postMessages are ignored", () => {
    const { result, iframe } = setup({ initialStage: "connected" });

    dispatch(iframe, { type: "CBROWSER_LIFECYCLE_STALE" }, { source: null });
    dispatch(
      iframe,
      { type: "CBROWSER_LIFECYCLE_STALE" },
      { origin: "https://evil.example" }
    );
    expect(result.current.reloadKey).toBe(0);
    expect(result.current.stage).toBe("connected");

    dispatch(iframe, { type: "CBROWSER_LIFECYCLE_STALE" });
    expect(result.current.reloadKey).toBe(1);
  });

  it("14. Web Locks unavailable has a dedicated diagnostic stage", () => {
    const { result, iframe } = setup({ initialStage: "connecting_signaling" });

    dispatch(iframe, { type: "CBROWSER_WEB_LOCKS_UNAVAILABLE" });

    expect(result.current.stage).toBe("web_locks_unavailable");
    expect(result.current.errorMessage).toContain("Web Locks");

    dispatch(iframe, {
      type: "CBROWSER_WS_CLOSE",
      code: 1008,
      reason: "tab_identity_unavailable",
    });
    expect(result.current.stage).toBe("web_locks_unavailable");
  });
});
