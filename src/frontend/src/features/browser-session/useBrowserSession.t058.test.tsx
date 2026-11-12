import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { useBrowserSession } from "./useBrowserSession";
import { I18nProvider, en } from "../../i18n";
import type { ApiClient } from "../../shared/api/client";

type SessionOptions = NonNullable<Parameters<typeof useBrowserSession>[2]>;

function makeMessage(
  iframe: HTMLIFrameElement,
  data: Record<string, unknown>,
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
  const getRuntime = vi.fn(async () => runtimeResponse("recovering"));
  const apiClient = { profiles: { getRuntime } } as unknown as ApiClient;
  const iframe = document.createElement("iframe");
  document.body.appendChild(iframe);
  const ref = { current: iframe } as React.RefObject<HTMLIFrameElement | null>;
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <I18nProvider>{children}</I18nProvider>
  );
  const rendered = renderHook(
    ({ opts }) => useBrowserSession("p1", ref, opts),
    {
      wrapper,
      initialProps: { opts: { apiClient, ...options } as SessionOptions },
    },
  );
  return { ...rendered, iframe, getRuntime, apiClient };
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

describe("useBrowserSession single runtime authority (t058 A25)", () => {
  it("AC-004: stage and error come from runtimeQuery input; the hook never reads runtime itself", async () => {
    const { result, getRuntime } = setup({ runtimeState: "running" });
    await waitFor(() =>
      expect(result.current.stage).toBe("connecting_signaling"),
    );
    expect(result.current.errorMessage).toBeNull();
    expect(getRuntime).not.toHaveBeenCalled();

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(getRuntime).not.toHaveBeenCalled();
  });

  it("AC-004: no runtime data yet means no error message, not a failed check", async () => {
    const { result, getRuntime } = setup({});
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(result.current.stage).toBe("checking_runtime");
    expect(result.current.errorMessage).toBeNull();
    expect(getRuntime).not.toHaveBeenCalled();
  });

  it("AC-004: a runtime error state yields the error stage and message from the same data", async () => {
    const { result } = setup({ runtimeState: "error" });
    await waitFor(() => expect(result.current.stage).toBe("error"));
    expect(result.current.errorMessage).toBe(
      en.runtimeReportedError.replace("{state}", "error"),
    );
  });

  it("AC-004: a stopped runtime yields runtime_not_ready with its message", async () => {
    const { result } = setup({ runtimeState: "stopped" });
    await waitFor(() =>
      expect(result.current.stage).toBe("runtime_not_ready"),
    );
    expect(result.current.errorMessage).toBe(
      en.runtimeNotRunning.replace("{state}", "stopped"),
    );
  });

  it("AC-004: runtime recovering to running reconnects from the error stage", async () => {
    const { result, rerender, apiClient } = setup({ runtimeState: "error" });
    await waitFor(() => expect(result.current.stage).toBe("error"));
    rerender({
      opts: { apiClient, runtimeState: "running" } as SessionOptions,
    });
    await waitFor(() => expect(result.current.reloadKey).toBe(1));
    await waitFor(() =>
      expect(result.current.stage).toBe("connecting_signaling"),
    );
  });
});

describe("useBrowserSession late frame guard (t058 A25, AC-005)", () => {
  function withFrames(iframe: HTMLIFrameElement) {
    const win = iframe.contentWindow as unknown as {
      __getWebRTCStats?: () => Promise<{
        video: { framesDecoded: number } | null;
        audio: null;
        pair: null;
        tab_id: null;
        connected: boolean;
        connectionState: string;
        iceConnectionState: string;
        signalingState: string;
      } | null>;
    };
    win.__getWebRTCStats = vi.fn(async () => ({
      video: {
        framesDecoded: 12,
        keyFramesDecoded: 1,
        bytesReceived: 10,
        packetsLost: 0,
        packetsReceived: 5,
      },
      audio: null,
      pair: null,
      tab_id: null,
      connected: true,
      connectionState: "connected",
      iceConnectionState: "connected",
      signalingState: "stable",
    }));
  }

  it("AC-005: late frames do not connect a stopped session and do not start audio", async () => {
    vi.useFakeTimers();
    const { result, iframe } = setup({
      initialStage: "media_no_frames",
      runtimeState: "stopped",
    });
    withFrames(iframe);
    const postMessage = vi.spyOn(iframe.contentWindow as Window, "postMessage");

    // Force the exact race the guard exists for: a frame signal arriving
    // while the backend is already stopped. (Normally the hook stops
    // sampling on a stopped runtime, so the signal is driven in through
    // the exposed diagnostics source instead of waiting for a tick.)
    await act(async () => {
      result.current.diagnosticsSource.setActive(true);
      await vi.advanceTimersByTimeAsync(1500);
    });

    expect(result.current.stage).toBe("media_no_frames");
    expect(postMessage).not.toHaveBeenCalled();
  });

  it("AC-005 control: the same frames connect the session while the runtime is running", async () => {
    vi.useFakeTimers();
    const { result, iframe } = setup({
      initialStage: "media_no_frames",
      runtimeState: "running",
    });
    withFrames(iframe);
    const postMessage = vi.spyOn(iframe.contentWindow as Window, "postMessage");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });

    expect(result.current.stage).toBe("connected");
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "pipelineControl",
        pipeline: "audio",
        enabled: true,
      }),
      expect.anything(),
    );
  });
});

describe("useBrowserSession pre-check WS_CLOSE guard (t058 A39, AC-007)", () => {
  it("AC-007: a WS 1006 close before the first runtime check only records, never recovers", async () => {
    const { result, iframe, getRuntime } = setup({});
    expect(result.current.stage).toBe("checking_runtime");

    dispatch(iframe, { type: "CBROWSER_WS_CLOSE", code: 1006 });

    expect(result.current.stage).toBe("checking_runtime");
    expect(result.current.reloadKey).toBe(0);
    expect(result.current.diagnostics.signalingCloseCode).toBe(1006);
    expect(getRuntime).not.toHaveBeenCalled();

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 100));
    });
    expect(result.current.stage).toBe("checking_runtime");
    expect(result.current.reloadKey).toBe(0);
    expect(getRuntime).not.toHaveBeenCalled();
  });

  it("AC-007: a first check settling to stopped keeps the diagnosed state", async () => {
    const { result, iframe, rerender, getRuntime, apiClient } = setup({});
    dispatch(iframe, { type: "CBROWSER_WS_CLOSE", code: 1006 });
    expect(getRuntime).not.toHaveBeenCalled();

    rerender({ opts: { apiClient, runtimeState: "stopped" } as SessionOptions });
    await waitFor(() =>
      expect(result.current.stage).toBe("runtime_not_ready"),
    );
    expect(result.current.errorMessage).toBeTruthy();
    expect(getRuntime).not.toHaveBeenCalled();
    expect(result.current.reloadKey).toBe(0);
  });

  it("AC-007: a first check settling to non-running cancels a same-generation recovery poll", async () => {
    const { result, iframe, rerender, getRuntime, apiClient } = setup({
      runtimeState: "running",
    });
    await waitFor(() =>
      expect(result.current.stage).toBe("connecting_signaling"),
    );

    dispatch(iframe, { type: "CBROWSER_WS_CLOSE", code: 1006 });
    await waitFor(() => expect(result.current.stage).toBe("reconnecting"));
    const callsBefore = getRuntime.mock.calls.length;
    expect(callsBefore).toBeGreaterThan(0);

    rerender({ opts: { apiClient, runtimeState: "stopped" } as SessionOptions });
    await waitFor(() =>
      expect(result.current.stage).toBe("runtime_not_ready"),
    );
    // Cover the 2000 ms transport poll interval: a live poll would call
    // getRuntime again here; a cancelled one stays silent.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 2100));
    });

    expect(getRuntime.mock.calls.length).toBe(callsBefore);
    expect(result.current.reloadKey).toBe(0);
  });
});
