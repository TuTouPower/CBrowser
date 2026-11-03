import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";
import { BrowserSessionView } from "./BrowserSessionView";
import { SessionDiagnostics } from "./SessionDiagnostics";
import { I18nProvider } from "../../i18n";

function renderView(ui: React.ReactElement) {
  return render(<I18nProvider>{ui}</I18nProvider>);
}

describe("per-page audio mute via official Selkies pipelineControl", () => {
  const profileId = "profile-media-1";

  beforeEach(() => {
    localStorage.setItem("cbm.locale", "zh");
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("sends STOP_AUDIO/START_AUDIO pipelineControl and toggles only this page", () => {
    renderView(<BrowserSessionView profileId={profileId} initialStage="connected" />);
    const iframe = screen.getByTestId("browser-session-iframe") as HTMLIFrameElement;
    const postMessage = vi.spyOn(iframe.contentWindow!, "postMessage");

    const button = screen.getByTestId("session-audio-toggle-btn");
    expect(button.getAttribute("data-audio-muted")).toBe("false");

    postMessage.mockClear();
    fireEvent.click(button);
    // The target origin is pinned to this page's own origin (A22): a bare
    // expect.any(String) would also accept "*" or a foreign origin.
    expect(postMessage).toHaveBeenCalledWith(
      { type: "pipelineControl", pipeline: "audio", enabled: false },
      window.location.origin
    );
    expect(button.getAttribute("data-audio-muted")).toBe("true");

    postMessage.mockClear();
    fireEvent.click(button);
    expect(postMessage).toHaveBeenCalledWith(
      { type: "pipelineControl", pipeline: "audio", enabled: true },
      window.location.origin
    );
    expect(button.getAttribute("data-audio-muted")).toBe("false");
  });

  it("does not mute another page instance", () => {
    renderView(
      <>
        <BrowserSessionView profileId="left" initialStage="connected" />
        <BrowserSessionView profileId="right" initialStage="connected" />
      </>
    );
    const buttons = screen.getAllByTestId("session-audio-toggle-btn");
    expect(buttons).toHaveLength(2);

    fireEvent.click(buttons[0]!);
    expect(buttons[0]?.getAttribute("data-audio-muted")).toBe("true");
    expect(buttons[1]?.getAttribute("data-audio-muted")).toBe("false");
  });
});

describe("audio diagnostics independent of the video stage", () => {
  beforeEach(() => {
    localStorage.setItem("cbm.locale", "zh");
  });

  afterEach(() => {
    localStorage.clear();
  });

  const base = {
    stage: "connected" as const,
    profileId: "profile-media-1",
    connectionState: "connected",
    iceConnectionState: "connected",
    signalingState: "stable",
  };

  it("shows no_data audio status while the video stage stays connected", () => {
    renderView(
      <BrowserSessionView
        profileId="profile-media-1"
        initialStage="connected"
        diagnostics={{ ...base, audioStatus: "no_data" }}
      />
    );
    fireEvent.click(screen.getByTestId("session-toggle-diag-btn"));
    expect(screen.getByTestId("session-stage-title").textContent).toContain("已连接");
    expect(screen.getByTestId("diag-audio-status").textContent).toContain(
      "音频无数据"
    );
  });

  it("renders every audio status label", () => {
    const expectations: Array<[string, string]> = [
      ["normal", "音频正常"],
      ["no_track", "无音频轨道"],
      ["no_data", "音频无数据"],
      ["unknown", "音频状态未知"],
      ["muted", "已静音"],
    ];
    for (const [status, text] of expectations) {
      const { unmount } = renderView(
        <SessionDiagnostics
          stage="connected"
          diagnostics={{ ...base, audioStatus: status as never }}
        />
      );
      expect(screen.getByTestId("diag-audio-status").textContent).toContain(text);
      unmount();
    }
  });

  it("renders localized labels in English when the locale is en", () => {
    localStorage.setItem("cbm.locale", "en");
    const { unmount } = renderView(
      <SessionDiagnostics
        stage="ice_failed"
        diagnostics={{ ...base, iceConnectionState: "failed", audioStatus: "unknown" }}
      />
    );
    expect(screen.getByTestId("session-stage-title").textContent).toContain(
      "ICE Connection Failed"
    );
    expect(screen.getByTestId("diag-audio-status").textContent).toContain(
      "Audio status unknown"
    );
    unmount();
  });
});
