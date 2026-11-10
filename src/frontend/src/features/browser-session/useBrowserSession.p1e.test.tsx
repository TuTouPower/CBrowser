import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import React from "react";
import { useBrowserSession } from "./useBrowserSession";
import { I18nProvider } from "../../i18n";
import type { ApiClient } from "../../shared/api/client";

type SessionOptions = NonNullable<Parameters<typeof useBrowserSession>[2]>;

function setup(options: Partial<SessionOptions> = {}, profileId = "p1") {
  const getRuntime = vi.fn(async () => ({
    profile_id: profileId,
    display_number: 1,
    desired_state: "running",
    observed_state: "running",
  }));
  const apiClient = { profiles: { getRuntime } } as unknown as ApiClient;
  const iframe = document.createElement("iframe");
  document.body.appendChild(iframe);
  const ref = { current: iframe } as React.RefObject<HTMLIFrameElement | null>;
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <I18nProvider>{children}</I18nProvider>
  );
  const rendered = renderHook(
    ({ pid, opts }) => useBrowserSession(pid, ref, opts),
    {
      wrapper,
      initialProps: { pid: profileId, opts: { apiClient, ...options } as SessionOptions },
    }
  );
  return { ...rendered, iframe, getRuntime, ref };
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

describe("useBrowserSession P1-E recovery", () => {
  it("starting -> running 推进 reconnect（reloadKey+1）", () => {
    const { result, rerender } = setup(
      { initialStage: "connecting_signaling", runtimeState: "starting" },
      "p1"
    );
    expect(result.current.reloadKey).toBe(0);
    rerender({
      pid: "p1",
      opts: {
        initialStage: "connecting_signaling",
        runtimeState: "running",
      } as SessionOptions,
    });
    expect(result.current.reloadKey).toBe(1);
    expect(result.current.stage).toBe("reconnecting");
  });

  it("media_no_frames 有帧可回 connected，无需手动 Reconnect 并清错误", async () => {
    vi.useFakeTimers();
    const { result, iframe } = setup({ initialStage: "media_no_frames" });
    // 超时错误文案先存在（media_no_frames 由超时进入时带错误）。
    expect(result.current.stage).toBe("media_no_frames");

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
      video: { framesDecoded: 12, keyFramesDecoded: 1, bytesReceived: 10, packetsLost: 0, packetsReceived: 5 },
      audio: null,
      pair: null,
      tab_id: null,
      connected: true,
      connectionState: "connected",
      iceConnectionState: "connected",
      signalingState: "stable",
    }));

    // P1-E：可恢复态保持采样，tick 后有帧即回 connected。
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });
    expect(result.current.stage).toBe("connected");
    expect(result.current.errorMessage).toBeNull();
    // 无需手动 Reconnect：reloadKey 未变。
    expect(result.current.reloadKey).toBe(0);
  });

  it("跨 Profile 切换重置 prevRuntimeRef，不误触发 reload", () => {
    const { result, rerender } = setup(
      { initialStage: "connected", runtimeState: "stopped" },
      "p1"
    );
    expect(result.current.reloadKey).toBe(0);
    // 切到 p2 且新 runtime 为 running：若不重置，旧 stopped + 新 running
    // 会误触发一次 reconnect；重置后应视为初挂载，不触发。
    rerender({
      pid: "p2",
      opts: { initialStage: "connected", runtimeState: "running" } as SessionOptions,
    });
    expect(result.current.reloadKey).toBe(0);
  });
});
