import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { act, render, screen } from "@testing-library/react";
import { I18nProvider, en } from "../../i18n";
import { SessionDiagnosticsSource } from "./diagnostics_source";
import { SessionStagePanelConnected } from "./session_stage_panel_connected";
import { SESS_STAGE_PANEL } from "./session_keys";
import type { SelkiesStats, SessionDiagnosticsData } from "./types";

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

function video(
  framesDecoded: number,
  packetsLost: number,
  packetsReceived: number
): SelkiesStats["video"] {
  return {
    framesDecoded,
    keyFramesDecoded: 1,
    bytesReceived: 100,
    packetsLost,
    packetsReceived,
  };
}

function pair(): SelkiesStats["pair"] {
  return {
    localType: "host",
    remoteType: "srflx",
    remoteAddress: "127.0.0.1",
    remotePort: 443,
    remoteUfrag: "ufrag",
    roundTripTime: 0.025,
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

function makeDiagnostics(): SessionDiagnosticsData {
  return { stage: "media_waiting", profileId: "p1" };
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("cbrowser.locale", "en");
  Object.defineProperty(document, "hidden", {
    configurable: true,
    value: false,
  });
  vi.useFakeTimers({
    toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"],
  });
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = "";
  localStorage.clear();
});

describe("SessionStagePanelConnected high-frequency diagnostics (A40)", () => {
  it("feeds frames, packets and the candidate pair from live source samples", async () => {
    const controlled = new ControlledStats();
    const source = new SessionDiagnosticsSource({
      readStats: controlled.read,
      intervalMs: 1000,
    });

    render(
      <I18nProvider>
        <SessionStagePanelConnected
          stage="media_waiting"
          diagnostics={makeDiagnostics()}
          source={source}
          onReconnect={vi.fn()}
          onViewStatus={vi.fn()}
          onLaunch={vi.fn()}
        />
      </I18nProvider>
    );

    source.setActive(true);
    await advance(10);
    expect(controlled.calls).toBe(1);
    controlled.resolve(
      stats({
        connected: true,
        connectionState: "connected",
        iceConnectionState: "connected",
        signalingState: "stable",
        video: video(42, 3, 500),
        pair: pair(),
      })
    );
    await flush();

    const panel = screen.getByTestId(SESS_STAGE_PANEL);
    expect(panel.textContent).toContain(en.sessionDiagFramesDecoded);
    expect(panel.textContent).toContain("42");
    expect(panel.textContent).toContain(en.sessionDiagPacketsLost);
    expect(panel.textContent).toContain("3");
    expect(panel.textContent).toContain(en.sessionDiagPacketsReceived);
    expect(panel.textContent).toContain("500");
    expect(panel.textContent).toContain(en.sessionDiagCandidateType);
    expect(panel.textContent).toContain("host");
    expect(panel.textContent).toContain("srflx");
    expect(panel.textContent).toContain(en.sessionDiagRemoteEndpoint);
    expect(panel.textContent).toContain("127.0.0.1");
  });

  it("updates only the leaf on samples, leaving host renders and the iframe untouched", async () => {
    const controlled = new ControlledStats();
    const source = new SessionDiagnosticsSource({
      readStats: controlled.read,
      intervalMs: 1000,
    });
    let hostRenders = 0;

    function Host() {
      hostRenders += 1;
      return (
        <>
          <iframe
            key="session-iframe"
            data-testid="sess-iframe"
            src="/selkies/index.html?profileId=p1&_k=0"
            title="session"
          />
          <SessionStagePanelConnected
            stage="media_waiting"
            diagnostics={makeDiagnostics()}
            source={source}
          />
        </>
      );
    }

    const { container } = render(
      <I18nProvider>
        <Host />
      </I18nProvider>
    );
    const iframeBefore = container.querySelector("iframe");

    source.setActive(true);
    await advance(10);
    controlled.resolve(
      stats({ video: video(5, 0, 10), connectionState: "connected" })
    );
    await flush();
    expect(screen.getByTestId(SESS_STAGE_PANEL).textContent).toContain("5");

    const rendersAfterFirstSample = hostRenders;
    await advance(1000);
    controlled.resolve(
      stats({ video: video(6, 2, 20), connectionState: "connected" })
    );
    await flush();

    expect(screen.getByTestId(SESS_STAGE_PANEL).textContent).toContain("6");
    expect(hostRenders).toBe(rendersAfterFirstSample);
    expect(container.querySelector("iframe")).toBe(iframeBefore);
    expect(iframeBefore?.getAttribute("src")).toBe(
      "/selkies/index.html?profileId=p1&_k=0"
    );
  });
});
