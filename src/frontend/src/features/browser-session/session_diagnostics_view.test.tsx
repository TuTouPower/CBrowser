import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { act, render, screen, renderHook } from "@testing-library/react";
import React, { useSyncExternalStore } from "react";
import { I18nProvider } from "../../i18n";
import type { ApiClient } from "../../shared/api/client";
import { useBrowserSession } from "./useBrowserSession";
import { SessionDiagnosticsSource } from "./diagnostics_source";
import { DiagnosticsOverlay } from "./diagnostics_overlay";
import { sessId } from "./session_keys";
import type { SelkiesStats, SessionDiagnosticsData } from "./types";

type StatsWindow = Window & {
  __getWebRTCStats?: () => Promise<SelkiesStats | null>;
};

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

function video(framesDecoded: number, packetsLost = 0): SelkiesStats["video"] {
  return {
    framesDecoded,
    keyFramesDecoded: 1,
    bytesReceived: 100,
    packetsLost,
    packetsReceived: 10,
  };
}

function pair(roundTripTime: number): SelkiesStats["pair"] {
  return {
    localType: "host",
    remoteType: "srflx",
    remoteAddress: "127.0.0.1",
    remotePort: 443,
    remoteUfrag: "ufrag",
    roundTripTime,
    bytesReceived: 100,
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

function makeIframeRef(controlled: ControlledStats) {
  const iframe = document.createElement("iframe");
  document.body.appendChild(iframe);
  (iframe.contentWindow as StatsWindow).__getWebRTCStats = controlled.read;
  return { current: iframe } as React.RefObject<HTMLIFrameElement | null>;
}

function makeApiClient() {
  return {
    profiles: {
      getRuntime: vi.fn(async () => ({
        profile_id: "p1",
        display_number: 1,
        desired_state: "running",
        observed_state: "running",
      })),
    },
  } as unknown as ApiClient;
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("cbrowser.locale", "en");
  vi.useFakeTimers({
    toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"],
  });
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
  localStorage.clear();
});

describe("useBrowserSession diagnostics source integration (A40)", () => {
  it("exposes a stable source and generation that never change from samples", async () => {
    const controlled = new ControlledStats();
    const iframeRef = makeIframeRef(controlled);
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <I18nProvider>{children}</I18nProvider>
    );
    const { result, rerender } = renderHook(
      () => useBrowserSession("p1", iframeRef, { apiClient: makeApiClient() }),
      { wrapper }
    );

    expect(result.current.diagnosticsSource).toBeInstanceOf(
      SessionDiagnosticsSource
    );
    const source = result.current.diagnosticsSource;
    const generation = result.current.generation;
    const reloadKey = result.current.reloadKey;

    await advance(10);
    controlled.resolve(stats({ video: video(10), connectionState: "connected" }));
    await flush();
    rerender();
    controlled.resolve(stats({ video: video(20), connectionState: "connected" }));
    await flush();

    expect(result.current.diagnosticsSource).toBe(source);
    expect(result.current.generation).toBe(generation);
    expect(result.current.reloadKey).toBe(reloadKey);
  });

  it("sample growth re-renders only the diagnostics leaf, not the page or main bar", async () => {
    const controlled = new ControlledStats();
    const iframeRef = makeIframeRef(controlled);
    const apiClient = makeApiClient();
    let pageRenders = 0;
    let barRenders = 0;
    let leafRenders = 0;

    function MainBar() {
      barRenders += 1;
      return <div data-testid="main-bar">bar</div>;
    }

    function DiagnosticsLeaf({ source }: { source: SessionDiagnosticsSource }) {
      leafRenders += 1;
      const snapshot = useSyncExternalStore(source.subscribe, source.getSnapshot);
      return <span data-testid="frames">{snapshot.diagnostics.framesDecoded ?? "-"}</span>;
    }

    function Page() {
      pageRenders += 1;
      const session = useBrowserSession("p1", iframeRef, {
        apiClient,
        initialStage: "connected",
      });
      return (
        <>
          <MainBar />
          <DiagnosticsLeaf source={session.diagnosticsSource} />
        </>
      );
    }

    render(
      <I18nProvider>
        <Page />
      </I18nProvider>
    );

    await advance(10);
    expect(controlled.calls).toBe(1);
    controlled.resolve(stats({ video: video(5), connectionState: "connected" }));
    await flush();
    expect(screen.getByTestId("frames")).toHaveTextContent("5");

    pageRenders = 0;
    barRenders = 0;
    leafRenders = 0;

    await advance(1000);
    controlled.resolve(
      stats({
        video: video(6, 2),
        pair: pair(0.03),
        connectionState: "connected",
      })
    );
    await flush();

    expect(screen.getByTestId("frames")).toHaveTextContent("6");
    expect(leafRenders).toBeGreaterThan(0);
    expect(pageRenders).toBe(0);
    expect(barRenders).toBe(0);
  });

  it("the diagnostics leaf renders correct formatted values from the source", async () => {
    const controlled = new ControlledStats();
    const source = new SessionDiagnosticsSource({
      readStats: controlled.read,
      intervalMs: 1000,
    });
    const diagnostics: SessionDiagnosticsData = {
      stage: "connected",
      profileId: "p1",
    };

    render(
      <I18nProvider>
        <DiagnosticsOverlay
          diagnostics={diagnostics}
          source={source}
          onClose={() => undefined}
        />
      </I18nProvider>
    );

    source.setActive(true);
    await advance(10);
    controlled.resolve(
      stats({
        connected: true,
        connectionState: "connected",
        iceConnectionState: "connected",
        signalingState: "stable",
        video: video(42, 3),
        pair: pair(0.025),
      })
    );
    await flush();

    expect(screen.getByTestId(sessId("diag", "conn-state"))).toHaveTextContent(
      "connected"
    );
    expect(
      screen.getByTestId(sessId("diag", "frames-decoded"))
    ).toHaveTextContent("42");
    expect(
      screen.getByTestId(sessId("diag", "packets-lost"))
    ).toHaveTextContent("3");
    expect(
      screen.getByTestId(sessId("diag", "round-trip-time"))
    ).toHaveTextContent("25");
  });
});
