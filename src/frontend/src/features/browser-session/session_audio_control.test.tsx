import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode, RefObject } from "react";
import {
  I18nProvider,
  en,
  useI18n,
  zh,
  type TranslationKey,
} from "../../i18n";
import {
  sendAudioPipelineControl,
  type AudioPipelineControlMessage,
} from "./audio_control";
import {
  AUDIO_STATUS_WINDOW_MS,
  deriveAudioStatus,
  type AudioStatus,
} from "./audio_status";
import { useBrowserSession } from "./useBrowserSession";

const wrapper = ({ children }: { children: ReactNode }) => (
  <I18nProvider>{children}</I18nProvider>
);

const PIPELINE_STOP = {
  type: "pipelineControl",
  pipeline: "audio",
  enabled: false,
} as const;
const PIPELINE_START = {
  type: "pipelineControl",
  pipeline: "audio",
  enabled: true,
} as const;

const dataChannelSend = vi.fn((_command: string) => undefined);

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("cbrowser.locale", "en");
  dataChannelSend.mockClear();

  class StubRTCDataChannel {
    send(command: string): void {
      dataChannelSend(command);
    }
  }
  class StubWebSocket {
    static readonly OPEN = 1;
    readyState = StubWebSocket.OPEN;
    send = vi.fn();
    close = vi.fn();
    addEventListener = vi.fn();
    removeEventListener = vi.fn();
  }
  vi.stubGlobal("WebSocket", StubWebSocket);
  vi.stubGlobal("RTCDataChannel", StubRTCDataChannel);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function makeIframeWindow() {
  const postMessage = vi.fn((message: AudioPipelineControlMessage) => {
    if (message.type === "pipelineControl" && message.pipeline === "audio") {
      const Channel = (
        globalThis as unknown as {
          RTCDataChannel: new () => { send(command: string): void };
        }
      ).RTCDataChannel;
      new Channel().send(message.enabled ? "START_AUDIO" : "STOP_AUDIO");
    }
  });
  const iframeRef = {
    current: { contentWindow: { postMessage } as unknown as Window },
  } as unknown as RefObject<HTMLIFrameElement | null>;
  return { iframeRef, postMessage };
}

describe("session audio control", () => {
  it("toggleAudio drives sendAudioPipelineControl with STOP_AUDIO/START_AUDIO", () => {
    const { iframeRef, postMessage } = makeIframeWindow();
    const { result, unmount } = renderHook(
      () => useBrowserSession("p1", iframeRef, { initialStage: "connected" }),
      { wrapper },
    );

    expect(postMessage).toHaveBeenCalledWith(
      PIPELINE_START,
      window.location.origin,
    );
    postMessage.mockClear();
    dataChannelSend.mockClear();

    act(() => result.current.toggleAudio());
    expect(result.current.audioMuted).toBe(true);
    expect(postMessage).toHaveBeenCalledWith(
      PIPELINE_STOP,
      window.location.origin,
    );
    expect(dataChannelSend).toHaveBeenCalledWith("STOP_AUDIO");

    postMessage.mockClear();
    dataChannelSend.mockClear();
    act(() => result.current.toggleAudio());
    expect(result.current.audioMuted).toBe(false);
    expect(postMessage).toHaveBeenCalledWith(
      PIPELINE_START,
      window.location.origin,
    );
    expect(dataChannelSend).toHaveBeenCalledWith("START_AUDIO");

    const directPost = vi.fn();
    const target = { postMessage: directPost } as unknown as Window;
    sendAudioPipelineControl(target, "https://viewer.example", false);
    expect(directPost).toHaveBeenCalledWith(
      PIPELINE_STOP,
      "https://viewer.example",
    );
    sendAudioPipelineControl(target, "https://viewer.example", true);
    expect(directPost).toHaveBeenLastCalledWith(
      PIPELINE_START,
      "https://viewer.example",
    );
    unmount();
  });

  it("two independent hook instances keep their own mute state", () => {
    const left = makeIframeWindow();
    const right = makeIframeWindow();
    const leftHook = renderHook(
      () =>
        useBrowserSession("left", left.iframeRef, {
          initialStage: "connected",
        }),
      { wrapper },
    );
    const rightHook = renderHook(
      () =>
        useBrowserSession("right", right.iframeRef, {
          initialStage: "connected",
        }),
      { wrapper },
    );

    left.postMessage.mockClear();
    right.postMessage.mockClear();
    dataChannelSend.mockClear();

    act(() => leftHook.result.current.toggleAudio());

    expect(leftHook.result.current.audioMuted).toBe(true);
    expect(rightHook.result.current.audioMuted).toBe(false);
    expect(left.postMessage).toHaveBeenCalledWith(
      PIPELINE_STOP,
      window.location.origin,
    );
    expect(right.postMessage).not.toHaveBeenCalled();
    expect(dataChannelSend).toHaveBeenCalledTimes(1);
    expect(dataChannelSend).toHaveBeenCalledWith("STOP_AUDIO");

    leftHook.unmount();
    rightHook.unmount();
  });

  it("covers all five AudioStatus values and their labels via deriveAudioStatus", () => {
    const now = 10_000;
    const sample = (
      at: number,
      present: boolean,
      bytesReceived: number,
      packetsReceived: number,
    ) => ({ at, present, bytesReceived, packetsReceived });
    const cases: Array<{
      status: AudioStatus;
      labelKey: TranslationKey;
      label: string;
      derive: () => AudioStatus;
    }> = [
      {
        status: "unknown",
        labelKey: "audioStatusUnknown",
        label: en.audioStatusUnknown,
        derive: () =>
          deriveAudioStatus([sample(now - 500, true, 100, 5)], now),
      },
      {
        status: "no_track",
        labelKey: "audioStatusNoTrack",
        label: en.audioStatusNoTrack,
        derive: () =>
          deriveAudioStatus(
            [
              sample(now - 3000, false, 0, 0),
              sample(now - 2000, false, 0, 0),
              sample(now, false, 0, 0),
            ],
            now,
          ),
      },
      {
        status: "no_data",
        labelKey: "audioStatusNoData",
        label: en.audioStatusNoData,
        derive: () =>
          deriveAudioStatus(
            [
              sample(now - 3000, true, 4096, 20),
              sample(now - 2000, true, 4096, 20),
              sample(now, true, 4096, 20),
            ],
            now,
          ),
      },
      {
        status: "normal",
        labelKey: "audioStatusNormal",
        label: en.audioStatusNormal,
        derive: () =>
          deriveAudioStatus(
            [
              sample(now - 3000, true, 4096, 20),
              sample(now - 2000, true, 8192, 40),
              sample(now, true, 12288, 60),
            ],
            now,
          ),
      },
      {
        status: "muted",
        labelKey: "audioStatusMuted",
        label: en.audioStatusMuted,
        derive: () =>
          deriveAudioStatus(
            [
              sample(now - 3000, true, 4096, 20),
              sample(now, true, 8192, 40),
            ],
            now,
            AUDIO_STATUS_WINDOW_MS,
            true,
          ),
      },
    ];

    const expected: Record<AudioStatus, string> = {
      unknown: "Audio status unknown",
      no_track: "No audio track",
      no_data: "No audio data",
      normal: "Audio OK",
      muted: "Audio muted",
    };
    const labels = new Set<string>();
    for (const { status, labelKey, label, derive } of cases) {
      expect(derive()).toBe(status);
      expect(en[labelKey]).toBe(expected[status]);
      expect(label.length).toBeGreaterThan(0);
      labels.add(label);
    }
    expect(labels.size).toBe(5);
  });

  it("resolves audioStatus* keys to English copy in the en locale", () => {
    localStorage.setItem("cbrowser.locale", "en");
    const keys: TranslationKey[] = [
      "audioStatusNormal",
      "audioStatusNoTrack",
      "audioStatusNoData",
      "audioStatusUnknown",
      "audioStatusMuted",
    ];
    const { result, unmount } = renderHook(() => useI18n(), { wrapper });
    expect(result.current.locale).toBe("en");
    for (const key of keys) {
      expect(result.current.t(key)).toBe(en[key]);
      expect(result.current.t(key)).not.toBe(zh[key]);
    }
    expect(result.current.t("audioStatusUnknown")).toBe(
      "Audio status unknown",
    );
    expect(result.current.t("audioStatusMuted")).toBe("Audio muted");
    unmount();
  });
});
