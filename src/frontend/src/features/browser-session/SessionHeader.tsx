import type { JSX } from "react";
import {
  Activity,
  Maximize2,
  PanelRight,
  Square,
  Volume2,
  VolumeX,
} from "lucide-react";
import { useI18n, type TranslationKey } from "../../i18n";
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
import { environmentStatusDescriptor } from "../../shared/presentation";
import {
  transportStateTone,
} from "./transport_state";
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
  isPending?: boolean;
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
  // t079 AC-002/AC-003: the header uses the same shared status
  // vocabulary as every other surface (running reads 运行中/Running);
  // a missing state is an explicit unknown, not a disguised stopped.
  const descriptor = environmentStatusDescriptor(observed);
  return { tone: descriptor.tone, label: t(descriptor.label) };
}

function headerTransportLabelKey(
  state: string | null | undefined,
): TranslationKey {
  // The header transport badge keeps its subject-carrying labels
  // (数据传输正常 / Data Ready) so transport stays distinguishable from
  // the environment status beside it (t079 AC-003); the details panel
  // uses the subject-less set from transport_state.ts under its own
  // field label. Same vocabulary roots, different surface subjects.
  switch (state) {
    case "ready":
      return "sessHeaderTransportReady";
    case "recovering":
      return "sessHeaderTransportRecovering";
    case "failed":
      return "sessHeaderTransportFailed";
    default:
      return "sessHeaderTransportUnknown";
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
    isPending = false,
    onAudioToggle,
    onDiagnosticsToggle,
    onDetailsToggle,
    onFocusToggle,
    onStop,
    onApplyRestart,
  } = props;
  const { t } = useI18n();
  const observed = observedStatus(runtime?.observed_state, t);
  const transportState = runtime?.transport?.transport_state;
  const applyPending = Boolean(
    runtime && runtime.config_version !== profile.current_config_version,
  );

  return (
    <header
      data-testid={SESS_HEADER}
      className="flex items-center gap-sm border-b border-outline bg-surface-raised px-sm py-xs"
    >
      <EnvironmentSwitcher
        currentProfileId={profile.id}
        profiles={profiles}
        groups={groups}
      />

      <div data-testid={OBSERVED_STATE_ID} className="flex items-center gap-xs">
        <StatusBadge tone={observed.tone} label={observed.label} />
      </div>

      <div data-testid={TRANSPORT_STATE_ID} className="flex items-center gap-xs">
        <StatusBadge
          tone={transportStateTone(transportState)}
          label={t(headerTransportLabelKey(transportState))}
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
            disabled={isPending}
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
            <VolumeX aria-hidden="true" className="size-(--component-icon-md-size)" />
          ) : (
            <Volume2 aria-hidden="true" className="size-(--component-icon-md-size)" />
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
          <Activity aria-hidden="true" className="size-(--component-icon-md-size)" />
        </IconButton>

        <IconButton
          label={detailsOpen ? t("sessDetailsClose") : t("sessDetailsOpen")}
          data-testid={SESS_DETAILS_TOGGLE}
          aria-pressed={detailsOpen}
          onClick={onDetailsToggle}
        >
          <PanelRight aria-hidden="true" className="size-(--component-icon-md-size)" />
        </IconButton>

        <IconButton
          label={t("sessFocus")}
          data-testid={FOCUS_TOGGLE_ID}
          aria-pressed={focusMode}
          onClick={onFocusToggle}
        >
          <Maximize2 aria-hidden="true" className="size-(--component-icon-md-size)" />
        </IconButton>

        <Button
          variant="danger"
          aria-label={t("sessStop")}
          data-testid={SESS_STOP}
          disabled={isPending}
          onClick={onStop}
        >
          <Square aria-hidden="true" className="size-(--component-icon-md-size)" />
        </Button>
      </div>
    </header>
  );
}
