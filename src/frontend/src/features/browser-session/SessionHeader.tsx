import type { JSX } from "react";
import {
  Activity,
  Maximize2,
  PanelRight,
  Square,
  Volume2,
  VolumeX,
} from "lucide-react";
import { useI18n } from "../../i18n";
import type {
  GroupResponse,
  ProfileResponse,
  ProfileRuntimeResponse,
} from "../../shared/api/types";
import {
  Banner,
  Button,
  IconButton,
  StatusBadge,
  type StatusTone,
} from "../../shared/ui";
import { EnvironmentSwitcher } from "./EnvironmentSwitcher";
import {
  SESS_APPLY_RESTART,
  SESS_AUDIO_TOGGLE,
  SESS_DIAG_TOGGLE,
  SESS_DETAILS_TOGGLE,
  SESS_HEADER,
  SESS_STOP,
} from "./session_keys";

export interface SessionHeaderProps {
  profile: ProfileResponse;
  runtime: ProfileRuntimeResponse | null;
  profiles: ProfileResponse[];
  groups: GroupResponse[];
  audioMuted: boolean;
  diagnosticsOpen: boolean;
  detailsOpen: boolean;
  focusMode: boolean;
  onAudioToggle: () => void;
  onDiagnosticsToggle: () => void;
  onDetailsToggle: () => void;
  onFocusToggle: () => void;
  onStop: () => void;
  onApplyRestart: () => void;
}

const OBSERVED_STATE_ID = "sess-observed-state";
const TRANSPORT_STATE_ID = "sess-transport-state";
const APPLY_PENDING_ID = "sess-apply-pending";
const FOCUS_TOGGLE_ID = "sess-focus-toggle";

function observedStatus(
  observed: ProfileRuntimeResponse["observed_state"] | undefined,
  t: ReturnType<typeof useI18n>["t"],
): { tone: StatusTone; label: string } {
  switch (observed) {
    case "running":
      return { tone: "running", label: t("sessRunning") };
    case "starting":
      return { tone: "transition", label: t("statusStarting") };
    case "stopping":
      return { tone: "transition", label: t("statusStopping") };
    case "error":
      return { tone: "error", label: t("statusError") };
    default:
      return { tone: "stopped", label: t("sessStopped") };
  }
}

function transportTone(state: string): StatusTone {
  switch (state) {
    case "ready":
      return "running";
    case "recovering":
      return "transition";
    case "failed":
      return "error";
    default:
      return "stopped";
  }
}

export function SessionHeader(props: SessionHeaderProps): JSX.Element {
  const {
    profile,
    runtime,
    profiles,
    groups,
    audioMuted,
    diagnosticsOpen,
    detailsOpen,
    focusMode,
    onAudioToggle,
    onDiagnosticsToggle,
    onDetailsToggle,
    onFocusToggle,
    onStop,
    onApplyRestart,
  } = props;
  const { t } = useI18n();
  const observed = observedStatus(runtime?.observed_state, t);
  const transportState = runtime?.transport?.transport_state ?? "unknown";
  const applyPending = Boolean(
    runtime && runtime.config_version !== profile.current_config_version,
  );

  return (
    <header
      data-testid={SESS_HEADER}
      className="flex items-center gap-md border-b border-outline bg-surface-raised px-md py-sm"
    >
      <EnvironmentSwitcher
        currentProfileId={profile.id}
        profiles={profiles}
        groups={groups}
      />

      <div data-testid={OBSERVED_STATE_ID} className="flex items-center gap-xs">
        <span className="font-ui text-label-sm text-on-surface-muted">
          {t("sessObservedState")}
        </span>
        <StatusBadge tone={observed.tone} label={observed.label} />
      </div>

      <div data-testid={TRANSPORT_STATE_ID} className="flex items-center gap-xs">
        <span className="font-ui text-label-sm text-on-surface-muted">
          {t("sessTransport")}
        </span>
        <StatusBadge
          tone={transportTone(transportState)}
          label={transportState}
        />
      </div>

      {applyPending && (
        <Banner tone="warning" testId={APPLY_PENDING_ID}>
          <span className="font-ui text-body-sm text-on-surface">
            {t("sessApplyPending")}
          </span>
          <Button
            size="sm"
            data-testid={SESS_APPLY_RESTART}
            onClick={onApplyRestart}
          >
            {t("sessApplyRestart")}
          </Button>
        </Banner>
      )}

      <div className="ml-auto flex items-center gap-xs">
        <IconButton
          label={audioMuted ? t("audioUnmute") : t("audioMute")}
          data-testid={SESS_AUDIO_TOGGLE}
          aria-pressed={audioMuted}
          onClick={onAudioToggle}
        >
          {audioMuted ? (
            <VolumeX aria-hidden="true" className="h-4 w-4" />
          ) : (
            <Volume2 aria-hidden="true" className="h-4 w-4" />
          )}
        </IconButton>

        <IconButton
          label={
            diagnosticsOpen
              ? t("sessionHideDiagnostics")
              : t("sessionToggleDiagnostics")
          }
          data-testid={SESS_DIAG_TOGGLE}
          aria-pressed={diagnosticsOpen}
          onClick={onDiagnosticsToggle}
        >
          <Activity aria-hidden="true" className="h-4 w-4" />
        </IconButton>

        <IconButton
          label={detailsOpen ? t("sessDetailsClose") : t("sessDetailsOpen")}
          data-testid={SESS_DETAILS_TOGGLE}
          aria-pressed={detailsOpen}
          onClick={onDetailsToggle}
        >
          <PanelRight aria-hidden="true" className="h-4 w-4" />
        </IconButton>

        <IconButton
          label={t("sessFocus")}
          data-testid={FOCUS_TOGGLE_ID}
          aria-pressed={focusMode}
          onClick={onFocusToggle}
        >
          <Maximize2 aria-hidden="true" className="h-4 w-4" />
        </IconButton>

        <Button
          variant="danger"
          aria-label={t("sessStop")}
          data-testid={SESS_STOP}
          onClick={onStop}
        >
          <Square aria-hidden="true" className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
