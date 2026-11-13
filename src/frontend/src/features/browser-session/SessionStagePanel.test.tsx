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

// t061 replacement note: the pre-t061 suite asserted that EVERY
// non-connected stage renders the centered diagnostic card with
// action buttons (the 364d191 visual contract). AC-002/AC-003 replace
// that contract with a stage matrix — waiting stages render only a
// lightweight indicator, fault/not-ready/stopping stages keep the
// diagnostic card with a per-stage action set — so the all-stage
// panel/reconnect assertions were replaced wholesale below instead of
// being edited to follow the new output.

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

const WAITING_STAGES: Array<{ stage: SessionStage; title: string }> = [
  { stage: "checking_runtime", title: en.sessionStageCheckingRuntime },
  { stage: "connecting_signaling", title: en.sessionStageConnectingSignaling },
  { stage: "media_waiting", title: en.sessionStageMediaWaiting },
  { stage: "reconnecting", title: en.sessionStageReconnecting },
];

const FAILURE_STAGES: SessionStage[] = [
  "signaling_failed",
  "ice_failed",
  "media_no_frames",
  "web_locks_unavailable",
  "error",
];

const CARD_STAGES: Array<{ stage: SessionStage; title: string }> = [
  { stage: "runtime_not_ready", title: en.sessionStageRuntimeNotReady },
  { stage: "stopping", title: en.sessionStageStopping },
  { stage: "signaling_failed", title: en.sessionStageSignalingFailed },
  {
    stage: "web_locks_unavailable",
    title: en.sessionStageWebLocksUnavailable,
  },
  { stage: "ice_failed", title: en.sessionStageIceFailed },
  { stage: "media_no_frames", title: en.sessionStageMediaNoFrames },
  { stage: "error", title: en.sessionStageError },
];

describe("SessionStagePanel", () => {
  it.each(WAITING_STAGES)(
    "waiting stage $stage shows only a lightweight indicator (AC-002)",
    ({ stage, title }) => {
      renderPanel({ stage });
      const panel = screen.getByTestId(SESS_STAGE_PANEL);
      expect(panel).toBeInTheDocument();
      expect(screen.getByTestId(SESS_STAGE_TITLE)).toHaveTextContent(title);
      // No centered diagnostic table and no action buttons while waiting.
      expect(
        screen.queryByTestId(sessId("stage", "diagnostics")),
      ).toBeNull();
      expect(screen.queryByTestId(SESS_STAGE_ACTION)).toBeNull();
      expect(actionButtons(panel)).toHaveLength(0);
      expect(panel.textContent).not.toContain(en.sessionDiagConnectionState);
    },
  );

  it.each(CARD_STAGES)(
    "diagnostic stage $stage keeps the card with diagnostics (AC-003)",
    ({ stage, title }) => {
      renderPanel({ stage });
      const panel = screen.getByTestId(SESS_STAGE_PANEL);
      expect(panel).toBeInTheDocument();
      expect(screen.getByTestId(SESS_STAGE_TITLE)).toHaveTextContent(title);
      expect(
        screen.getByTestId(sessId("stage", "diagnostics")),
      ).toBeInTheDocument();
      expect(panel.textContent).toContain(en.sessionDiagConnectionState);
      expect(screen.getByTestId(SESS_STAGE_ACTION)).toBeInTheDocument();
    },
  );

  it("renders nothing for the connected stage", () => {
    renderPanel({ stage: "connected" });
    expect(screen.queryByTestId(SESS_STAGE_PANEL)).toBeNull();
    expect(screen.queryByTestId(SESS_STAGE_TITLE)).toBeNull();
  });

  it("shows ICE/signaling/frames diagnostics on a failure stage", () => {
    renderPanel({
      stage: "ice_failed",
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

  it.each(FAILURE_STAGES)(
    "failure stage $stage offers reconnect and status, never launch (AC-003)",
    (stage) => {
      renderPanel({ stage });
      expect(
        screen.getByTestId(sessId("stage-action", "reconnect")),
      ).toBeInTheDocument();
      expect(
        screen.getByTestId(sessId("stage-action", "view-status")),
      ).toBeInTheDocument();
      expect(screen.queryByTestId(sessId("stage-action", "launch"))).toBeNull();
    },
  );

  it("stopping shows status only and never offers reconnect or launch", () => {
    renderPanel({ stage: "stopping" });
    expect(screen.getByTestId(SESS_STAGE_TITLE)).toHaveTextContent(
      en.sessionStageStopping,
    );
    expect(
      screen.queryByTestId(sessId("stage-action", "reconnect")),
    ).toBeNull();
    expect(screen.queryByTestId(sessId("stage-action", "launch"))).toBeNull();
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

  it("runtime_not_ready offers launch and status, not reconnect (AC-003)", () => {
    renderPanel({ stage: "runtime_not_ready" });
    expect(screen.getByTestId(SESS_STAGE_TITLE)).toHaveTextContent(
      en.sessionStageRuntimeNotReady,
    );
    expect(
      screen.getByTestId(sessId("stage-action", "launch")),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId(sessId("stage-action", "view-status")),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId(sessId("stage-action", "reconnect")),
    ).toBeNull();
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
