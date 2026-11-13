import type { JSX } from "react";
import { CircleX, LoaderCircle } from "lucide-react";
import { useI18n, type TranslationKey } from "../../i18n";
import { Banner, Button, MonoValue } from "../../shared/ui";
import {
  SESS_STAGE_ACTION,
  SESS_STAGE_PANEL,
  SESS_STAGE_TITLE,
  sessId,
} from "./session_keys";
import type { SessionDiagnosticsData, SessionStage } from "./types";

export interface SessionStagePanelProps {
  stage: SessionStage;
  diagnostics: SessionDiagnosticsData | null;
  onReconnect?: () => void;
  onViewStatus?: () => void;
  onLaunch?: () => void;
}

type StageKey = SessionStage | "connecting_ice";
type ActionId = "reconnect" | "view-status" | "launch";

const STAGE_TITLE_KEYS: Record<StageKey, TranslationKey> = {
  checking_runtime: "sessionStageCheckingRuntime",
  runtime_not_ready: "sessionStageRuntimeNotReady",
  stopping: "sessionStageStopping",
  connecting_signaling: "sessionStageConnectingSignaling",
  signaling_failed: "sessionStageSignalingFailed",
  web_locks_unavailable: "sessionStageWebLocksUnavailable",
  ice_failed: "sessionStageIceFailed",
  media_waiting: "sessionStageMediaWaiting",
  media_no_frames: "sessionStageMediaNoFrames",
  connected: "sessionStageConnected",
  reconnecting: "sessionStageReconnecting",
  error: "sessionStageError",
  connecting_ice: "sessionStageConnectingSignaling",
};

const RECONNECT_EXEMPT_STAGES: readonly StageKey[] = [
  "stopping",
  "reconnecting",
];
const LAUNCH_STAGES: readonly StageKey[] = [
  "checking_runtime",
  "runtime_not_ready",
  "ice_failed",
  "error",
];

function stageActions(stage: StageKey): ActionId[] {
  if (RECONNECT_EXEMPT_STAGES.includes(stage)) return ["view-status"];
  const actions: ActionId[] = ["reconnect", "view-status"];
  if (LAUNCH_STAGES.includes(stage)) actions.push("launch");
  return actions;
}

const ACTION_LABEL_KEYS: Record<ActionId, TranslationKey> = {
  reconnect: "sessionReconnect",
  "view-status": "sessionViewStatus",
  launch: "launchRemoteBrowser",
};

const ERROR_STAGES: StageKey[] = [
  "runtime_not_ready",
  "signaling_failed",
  "web_locks_unavailable",
  "ice_failed",
  "media_no_frames",
  "error",
];

interface DiagnosticRow {
  labelKey: TranslationKey;
  value: string | number;
}

function diagnosticRows(diagnostics: SessionDiagnosticsData | null): DiagnosticRow[] {
  const rows: DiagnosticRow[] = [];
  if (!diagnostics) return rows;
  const add = (
    labelKey: TranslationKey,
    value: string | number | null | undefined,
  ) => {
    if (value !== undefined && value !== null && value !== "") {
      rows.push({ labelKey, value });
    }
  };
  add("sessionDiagConnectionState", diagnostics.connectionState);
  add("sessionDiagIceState", diagnostics.iceConnectionState);
  add("sessionDiagSignalingState", diagnostics.signalingState);
  add("sessionDiagFramesDecoded", diagnostics.framesDecoded);
  add("sessionDiagPacketsLost", diagnostics.packetsLost);
  add("sessionDiagPacketsReceived", diagnostics.packetsReceived);
  const pair = diagnostics.selectedPair;
  if (pair) {
    add(
      "sessionDiagCandidateType",
      `${pair.localType ?? "unknown"} → ${pair.remoteType ?? "unknown"}`,
    );
    add(
      "sessionDiagRemoteEndpoint",
      pair.remoteAddress && pair.remotePort !== null
        ? `${pair.remoteAddress}:${pair.remotePort}`
        : pair.remoteAddress,
    );
  }
  return rows;
}

export function SessionStagePanel(props: SessionStagePanelProps): JSX.Element {
  const { t } = useI18n();
  const { stage, diagnostics, onReconnect, onViewStatus, onLaunch } = props;

  if (stage === "connected") return <></>;

  const stageKey = stage as StageKey;
  const titleKey = STAGE_TITLE_KEYS[stageKey] ?? "sessionStageError";
  const actionIds = stageActions(stageKey);
  const isError = ERROR_STAGES.includes(stageKey);
  const rows = diagnosticRows(diagnostics);

  const callbacks: Record<ActionId, (() => void) | undefined> = {
    reconnect: onReconnect,
    "view-status": onViewStatus,
    launch: onLaunch,
  };
  const actions = actionIds
    .map((id) => ({ id, callback: callbacks[id] }))
    .filter(
      (action): action is { id: ActionId; callback: () => void } =>
        action.callback !== undefined,
    );

  return (
    <div
      data-testid={SESS_STAGE_PANEL}
      className="pointer-events-none absolute inset-none flex items-center justify-center p-lg"
    >
      <div className="pointer-events-auto flex w-full max-w-panel flex-col gap-md rounded-lg border border-outline bg-surface p-lg">
        <div className="flex items-center gap-sm">
          {isError ? (
            <CircleX aria-hidden="true" className="size-(--component-icon-md-size) shrink-0 text-danger" />
          ) : (
            <LoaderCircle
              aria-hidden="true"
              className="size-(--component-icon-md-size) shrink-0 animate-pulse text-accent"
            />
          )}
          <h2
            data-testid={SESS_STAGE_TITLE}
            className="font-ui text-headline-md text-on-surface"
          >
            {t(titleKey)}
          </h2>
        </div>

        {diagnostics?.errorMessage && (
          <Banner tone="danger">{diagnostics.errorMessage}</Banner>
        )}

        <dl
          data-testid={sessId("stage", "diagnostics")}
          className="flex flex-col gap-xs rounded-md border border-outline bg-surface-subtle px-md py-sm"
        >
          {rows.length === 0 ? (
            <div className="flex justify-between gap-sm">
              <dt className="font-ui text-label-sm text-on-surface-muted">
                {t("sessObservedState")}
              </dt>
              <dd>
                <MonoValue>{t(titleKey)}</MonoValue>
              </dd>
            </div>
          ) : (
            rows.map((row) => (
              <div key={row.labelKey} className="flex justify-between gap-sm">
                <dt className="font-ui text-label-sm text-on-surface-muted">
                  {t(row.labelKey)}
                </dt>
                <dd>
                  <MonoValue>{row.value}</MonoValue>
                </dd>
              </div>
            ))
          )}
        </dl>

        <div data-testid={SESS_STAGE_ACTION} className="flex flex-wrap gap-sm">
          {actions.length === 0 ? (
            <p
              data-testid={sessId("stage-action", "hint")}
              className="font-ui text-body-sm text-on-surface-muted"
            >
              {t("sessionViewStatus")}
            </p>
          ) : (
            actions.map((action, index) => (
              <Button
                key={action.id}
                type="button"
                variant={index === 0 ? "primary" : "secondary"}
                data-testid={sessId("stage-action", action.id)}
                onClick={action.callback}
              >
                {t(ACTION_LABEL_KEYS[action.id])}
              </Button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
