import { describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { I18nProvider, en } from "../../i18n";
import {
  SessionStagePanel,
  type SessionStagePanelProps,
} from "./SessionStagePanel";
import {
  SESS_STAGE_ACTION,
  SESS_STAGE_PANEL,
  SESS_STAGE_TITLE,
  sessId,
} from "./session_keys";
import type { SessionDiagnosticsData, SessionStage } from "./types";

function diagnostics(
  overrides: Partial<SessionDiagnosticsData> = {},
): SessionDiagnosticsData {
  return {
    stage: "checking_runtime",
    profileId: "p1",
    connectionState: "connecting",
    iceConnectionState: "checking",
    signalingState: "have-local-offer",
    framesDecoded: 0,
    packetsLost: 0,
    ...overrides,
  };
}

function renderPanel(overrides: Partial<SessionStagePanelProps> = {}) {
  const props: SessionStagePanelProps = {
    stage: "checking_runtime",
    diagnostics: diagnostics(),
    onReconnect: vi.fn(),
    onViewStatus: vi.fn(),
    onLaunch: vi.fn(),
    ...overrides,
  };
  const view = render(
    <I18nProvider>
      <SessionStagePanel {...props} />
    </I18nProvider>,
  );
  return { ...view, props };
}

function actionButtons(container: HTMLElement): HTMLElement[] {
  return Array.from(
    container.querySelectorAll<HTMLElement>(
      '[data-testid^="sess-stage-action-"]',
    ),
  );
}

const NON_CONNECTED: Array<{ stage: SessionStage; title: string }> = [
  { stage: "checking_runtime", title: en.sessionStageCheckingRuntime },
  { stage: "connecting_signaling", title: en.sessionStageConnectingSignaling },
  { stage: "media_waiting", title: en.sessionStageMediaWaiting },
  { stage: "reconnecting", title: en.sessionStageReconnecting },
  { stage: "ice_failed", title: en.sessionStageIceFailed },
  { stage: "error", title: en.sessionStageError },
];

const ALL_PANEL_STAGES: Array<{ stage: SessionStage; reason: string }> = [
  { stage: "checking_runtime", reason: en.sessionStageCheckingRuntime },
  { stage: "runtime_not_ready", reason: en.sessionStageRuntimeNotReady },
  { stage: "stopping", reason: en.sessionStageStopping },
  { stage: "connecting_signaling", reason: en.sessionStageConnectingSignaling },
  { stage: "signaling_failed", reason: en.sessionStageSignalingFailed },
  {
    stage: "web_locks_unavailable",
    reason: en.sessionStageWebLocksUnavailable,
  },
  { stage: "ice_failed", reason: en.sessionStageIceFailed },
  { stage: "media_waiting", reason: en.sessionStageMediaWaiting },
  { stage: "media_no_frames", reason: en.sessionStageMediaNoFrames },
  { stage: "reconnecting", reason: en.sessionStageReconnecting },
  { stage: "error", reason: en.sessionStageError },
  {
    stage: "connecting_ice" as unknown as SessionStage,
    reason: en.sessionStageConnectingSignaling,
  },
];

describe("SessionStagePanel", () => {
  it.each(NON_CONNECTED)(
    "shows a centered panel, reason title and action for $stage",
    ({ stage, title }) => {
      renderPanel({ stage });
      expect(screen.getByTestId(SESS_STAGE_PANEL)).toBeInTheDocument();
      expect(screen.getByTestId(SESS_STAGE_TITLE)).toHaveTextContent(title);
      expect(
        actionButtons(screen.getByTestId(SESS_STAGE_ACTION)).length,
      ).toBeGreaterThan(0);
    },
  );

  it("renders nothing for the connected stage", () => {
    renderPanel({ stage: "connected" });
    expect(screen.queryByTestId(SESS_STAGE_PANEL)).toBeNull();
    expect(screen.queryByTestId(SESS_STAGE_TITLE)).toBeNull();
  });

  it("keeps a visible panel for every non-error connecting stage", () => {
    for (const { stage, reason } of ALL_PANEL_STAGES) {
      const view = renderPanel({ stage });
      const panel = screen.getByTestId(SESS_STAGE_PANEL);
      expect(panel).toBeInTheDocument();
      expect(screen.getByTestId(SESS_STAGE_TITLE)).toBeInTheDocument();
      expect(panel.textContent).toContain(reason);
      expect(panel.textContent).toContain(en.sessionDiagConnectionState);
      const actionRegion = screen.getByTestId(SESS_STAGE_ACTION);
      expect(
        actionButtons(actionRegion).length > 0 ||
          screen.queryByTestId(sessId("stage-action", "hint")) !== null,
      ).toBe(true);
      view.unmount();
    }
  });

  it("handles the future connecting_ice string literal", () => {
    renderPanel({ stage: "connecting_ice" as unknown as SessionStage });
    const panel = screen.getByTestId(SESS_STAGE_PANEL);
    expect(panel).toBeInTheDocument();
    expect(screen.getByTestId(SESS_STAGE_TITLE)).toBeInTheDocument();
    expect(screen.getByTestId(SESS_STAGE_ACTION).textContent).toContain(
      en.sessionViewStatus,
    );
    expect(panel.textContent).toContain(en.sessionDiagIceState);
  });

  it("shows ICE/signaling/frames diagnostics as the reason", () => {
    renderPanel({
      stage: "media_waiting",
      diagnostics: diagnostics({
        iceConnectionState: "checking",
        signalingState: "stable",
        framesDecoded: 0,
      }),
    });
    const panel = screen.getByTestId(SESS_STAGE_PANEL);
    expect(panel.textContent).toContain(en.sessionDiagIceState);
    expect(panel.textContent).toContain("checking");
    expect(panel.textContent).toContain(en.sessionDiagSignalingState);
    expect(panel.textContent).toContain("stable");
    expect(panel.textContent).toContain(en.sessionDiagFramesDecoded);
  });

  it("invokes the stage action callbacks", () => {
    const { props } = renderPanel({ stage: "ice_failed" });
    fireEvent.click(screen.getByTestId(sessId("stage-action", "reconnect")));
    expect(props.onReconnect).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId(sessId("stage-action", "view-status")));
    expect(props.onViewStatus).toHaveBeenCalledTimes(1);
  });

  it("shows a text hint instead of crashing when all callbacks are missing", () => {
    renderPanel({
      stage: "signaling_failed",
      onReconnect: undefined,
      onViewStatus: undefined,
      onLaunch: undefined,
    });
    expect(screen.getByTestId(SESS_STAGE_PANEL)).toBeInTheDocument();
    expect(
      screen.getByTestId(sessId("stage-action", "hint")),
    ).toBeInTheDocument();
  });

  it("uses at most one primary action button", () => {
    renderPanel({ stage: "error" });
    const primary = actionButtons(
      screen.getByTestId(SESS_STAGE_ACTION),
    ).filter((button) => button.className.includes("bg-accent"));
    expect(primary.length).toBeLessThanOrEqual(1);
  });

  it("surfaces the diagnostic error message", () => {
    renderPanel({
      stage: "error",
      diagnostics: diagnostics({ errorMessage: "coordinator offline" }),
    });
    expect(screen.getByRole("alert").textContent).toContain(
      "coordinator offline",
    );
  });

  it("stopping shows status only and never offers reconnect", () => {
    renderPanel({ stage: "stopping" });
    expect(screen.getByTestId(SESS_STAGE_TITLE)).toHaveTextContent(
      en.sessionStageStopping,
    );
    expect(
      screen.queryByTestId(sessId("stage-action", "reconnect")),
    ).toBeNull();
    expect(
      screen.getByTestId(sessId("stage-action", "view-status")),
    ).toBeInTheDocument();
  });

  it("error offers both reconnect and status actions", () => {
    renderPanel({ stage: "error" });
    expect(screen.getByTestId(SESS_STAGE_TITLE)).toHaveTextContent(
      en.sessionStageError,
    );
    expect(
      screen.getByTestId(sessId("stage-action", "reconnect")),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId(sessId("stage-action", "view-status")),
    ).toBeInTheDocument();
  });

  it("media_no_frames is a recoverable error with reconnect but no relaunch", () => {
    renderPanel({ stage: "media_no_frames" });
    expect(screen.getByTestId(SESS_STAGE_TITLE)).toHaveTextContent(
      en.sessionStageMediaNoFrames,
    );
    expect(
      screen.getByTestId(sessId("stage-action", "reconnect")),
    ).toBeInTheDocument();
    expect(screen.queryByTestId(sessId("stage-action", "launch"))).toBeNull();
  });

  it("web_locks_unavailable offers reconnect and status without relaunch", () => {
    renderPanel({ stage: "web_locks_unavailable" });
    expect(screen.getByTestId(SESS_STAGE_TITLE)).toHaveTextContent(
      en.sessionStageWebLocksUnavailable,
    );
    expect(
      screen.getByTestId(sessId("stage-action", "reconnect")),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId(sessId("stage-action", "view-status")),
    ).toBeInTheDocument();
    expect(screen.queryByTestId(sessId("stage-action", "launch"))).toBeNull();
  });

  it("runtime_not_ready offers a launch action to recover the runtime", () => {
    renderPanel({ stage: "runtime_not_ready" });
    expect(screen.getByTestId(SESS_STAGE_TITLE)).toHaveTextContent(
      en.sessionStageRuntimeNotReady,
    );
    expect(
      screen.getByTestId(sessId("stage-action", "launch")),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId(sessId("stage-action", "reconnect")),
    ).toBeInTheDocument();
  });

  it("surfaces the selected candidate pair type and remote endpoint", () => {
    renderPanel({
      stage: "ice_failed",
      diagnostics: diagnostics({
        selectedPair: {
          localType: "host",
          remoteType: "srflx",
          remoteAddress: "203.0.113.7",
          remotePort: 5004,
          remoteUfrag: "ufrag-1",
          roundTripTime: 0.012,
          bytesReceived: 1024,
        },
      }),
    });
    const panel = screen.getByTestId(SESS_STAGE_PANEL);
    expect(panel.textContent).toContain(en.sessionDiagCandidateType);
    expect(panel.textContent).toContain("host");
    expect(panel.textContent).toContain("srflx");
    expect(panel.textContent).toContain(en.sessionDiagRemoteEndpoint);
    expect(panel.textContent).toContain("203.0.113.7");
  });
});
