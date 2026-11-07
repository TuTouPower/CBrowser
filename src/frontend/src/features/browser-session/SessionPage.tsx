import { useCallback, useEffect, useRef, useState } from "react";
import type { JSX } from "react";
import { useNavigate, useParams } from "react-router";
import { useI18n } from "../../i18n";
import { ApiError } from "../../shared/api/client";
import { useApiClient } from "../../shared/api/client_context";
import { Banner, Button, MonoValue } from "../../shared/ui";
import {
  useProfileQuery,
  useProfileRuntimeQuery,
  useProfilesQuery,
  useGroupsQuery,
  useProxiesQuery,
  useFontSetsQuery,
  useSetDesiredStateMutation,
  useStopProfileMutation,
  useApplyDisplaySettingsMutation,
} from "../profiles/useProfilesQuery";
import { useBrowserSession } from "./useBrowserSession";
import type { SessionDiagnosticsData, SessionStage } from "./types";
import {
  SESS_PAGE,
  SESS_STAGE,
  SESS_IFRAME,
  sessId,
} from "./session_keys";
import { useSessionFocus } from "./session_focus";
import { SessionHeader } from "./SessionHeader";
import { SessionStagePanel } from "./SessionStagePanel";
import { SessionDetailsPanel } from "./SessionDetailsPanel";
import { FocusModeToolbar } from "./FocusModeToolbar";
import { ClipboardPermissionHint } from "./ClipboardPermissionHint";

const DETAILS_OPEN_KEY = "cbrowser.session.details_open";
const SESSION_TARGET_KEY = "cbrowser.session.target";

function readDetailsOpen(): boolean {
  try {
    return localStorage.getItem(DETAILS_OPEN_KEY) === "1";
  } catch {
    return false;
  }
}

function CenteredMessage({ testId, text }: { testId: string; text: string }): JSX.Element {
  return (
    <div data-testid={testId} className="flex flex-1 items-center justify-center p-lg">
      <span className="font-ui text-body-md text-on-surface-muted">{text}</span>
    </div>
  );
}

function LoadErrorView({
  testId,
  message,
  onRetry,
}: {
  testId: string;
  message: string;
  onRetry: () => void;
}): JSX.Element {
  const { t } = useI18n();
  return (
    <div data-testid={testId} className="flex flex-1 flex-col items-center justify-center gap-md p-lg">
      <span className="font-ui text-body-md text-danger">{t("sessionLoadFailed", { error: message })}</span>
      <Button variant="primary" data-testid={sessId("load-retry", "profile")} onClick={onRetry}>
        {t("retryAction")}
      </Button>
    </div>
  );
}

function DiagnosticsOverlay({
  diagnostics,
  onClose,
}: {
  diagnostics: SessionDiagnosticsData;
  onClose: () => void;
}): JSX.Element {
  const { t } = useI18n();
  const audioLabels: Record<string, string> = {
    normal: t("audioStatusNormal"),
    no_track: t("audioStatusNoTrack"),
    no_data: t("audioStatusNoData"),
    unknown: t("audioStatusUnknown"),
    muted: t("audioStatusMuted"),
  };
  const audioStatus = diagnostics.audioStatus
    ? audioLabels[diagnostics.audioStatus] ?? diagnostics.audioStatus
    : "-";
  const rows: Array<{
    label: string;
    value: string | number;
    testId: string;
  }> = [
    { label: t("sessionDiagConnectionState"), value: diagnostics.connectionState ?? "-", testId: sessId("diag", "conn-state") },
    { label: t("sessionDiagIceState"), value: diagnostics.iceConnectionState ?? "-", testId: sessId("diag", "ice-state") },
    { label: t("sessionDiagSignalingState"), value: diagnostics.signalingState ?? "-", testId: sessId("diag", "signaling-state") },
    { label: t("sessionDiagAudioStatus"), value: audioStatus, testId: sessId("diag", "audio-status") },
    { label: t("sessionDiagFramesDecoded"), value: diagnostics.framesDecoded ?? "-", testId: sessId("diag", "frames-decoded") },
    { label: t("sessionDiagPacketsLost"), value: diagnostics.packetsLost ?? "-", testId: sessId("diag", "packets-lost") },
    { label: t("sessionDiagRoundTripTime"), value: diagnostics.roundTripTime ?? "-", testId: sessId("diag", "round-trip-time") },
  ];
  return (
    <div
      data-testid={sessId("diag", "overlay")}
      className="pointer-events-none absolute inset-0 flex justify-end p-md"
    >
      <div className="pointer-events-auto flex w-details self-start flex-col gap-sm rounded-lg border border-outline bg-surface p-md">
        <div className="flex items-center justify-between gap-sm">
          <h3 className="font-ui text-title-sm text-on-surface">{t("sessDiagnostics")}</h3>
          <Button variant="ghost" size="sm" data-testid={sessId("diag", "close")} onClick={onClose}>
            {t("sessionHideDiagnostics")}
          </Button>
        </div>
        {diagnostics.errorMessage ? (
          <Banner tone="danger">{diagnostics.errorMessage}</Banner>
        ) : null}
        <dl className="flex flex-col gap-xs">
          {rows.map((row) => (
            <div key={row.label} className="flex justify-between gap-sm">
               <dt className="font-ui text-label-sm text-on-surface-muted">{row.label}</dt>
              <dd data-testid={row.testId}>
                <MonoValue>{row.value}</MonoValue>
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}

export function SessionPage(): JSX.Element {
  const { profileId } = useParams<{ profileId: string }>();
  const id = profileId ?? "";
  const { t } = useI18n();
  const client = useApiClient();
  const navigate = useNavigate();
  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  useEffect(() => {
    if (!profileId) return;
    try {
      sessionStorage.setItem(SESSION_TARGET_KEY, profileId);
    } catch {
      return;
    }
  }, [profileId]);

  const profileQuery = useProfileQuery(profileId, client);
  const runtimeQuery = useProfileRuntimeQuery(profileId, client);
  const profilesQuery = useProfilesQuery(client);
  const groupsQuery = useGroupsQuery(client);
  const proxiesQuery = useProxiesQuery(client);
  const fontSetsQuery = useFontSetsQuery(client);

  const session = useBrowserSession(id, iframeRef, { apiClient: client });

  const [detailsOpen, setDetailsOpen] = useState(readDetailsOpen);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const { focusMode, setFocusMode } = useSessionFocus();

  const setDesiredStateMutation = useSetDesiredStateMutation(client);
  const stopMutation = useStopProfileMutation(client);
  const applyMutation = useApplyDisplaySettingsMutation(client);

  const handleDetailsOpenChange = useCallback((open: boolean) => {
    setDetailsOpen(open);
    try {
      localStorage.setItem(DETAILS_OPEN_KEY, open ? "1" : "0");
    } catch {
      return;
    }
  }, []);

  const profile = profileQuery.data ?? null;
  const runtime = runtimeQuery.data ?? null;
  // t039: single stage source. The host bridges the live API observed_state
  // onto the WebRTC session stage so every consumer (stage panel, data-stage
  // on the shell / stage wrapper / iframe, diagnostics view) sees one value.
  // stopping, error and stopped each map to their own stage with the right
  // recovery actions instead of being flattened to runtime_not_ready.
  const stage: SessionStage =
    runtime?.observed_state === "stopping"
      ? "stopping"
      : runtime?.observed_state === "error"
        ? "error"
        : runtime &&
            runtime.observed_state !== "running" &&
            runtime.observed_state !== "starting"
          ? "runtime_not_ready"
          : session.stage;
  const diagnosticsView: SessionDiagnosticsData = {
    ...session.diagnostics,
    stage,
    errorMessage: session.errorMessage ?? session.diagnostics.errorMessage,
  };
  const profileErrorStatus =
    profileQuery.error instanceof ApiError ? profileQuery.error.status : undefined;

  let pageBody: JSX.Element;
  if (!profileId) {
    pageBody = <CenteredMessage testId={sessId("select", "profile")} text={t("sessionSelectHint")} />;
  } else if (profileQuery.isLoading || runtimeQuery.isLoading) {
    pageBody = <CenteredMessage testId={sessId("loading", id)} text={t("sessionStageCheckingRuntime")} />;
  } else if (profileQuery.isError && profileErrorStatus !== 404) {
    pageBody = (
      <LoadErrorView
        testId={sessId("load-error", id)}
        message={profileQuery.error?.message ?? t("runtimeStateUnknown")}
        onRetry={() => profileQuery.refetch()}
      />
    );
  } else if (!profile) {
    pageBody = <CenteredMessage testId={sessId("not-found", id)} text={t("profileNotFound")} />;
  } else if (runtimeQuery.isError) {
    pageBody = (
      <LoadErrorView
        testId={sessId("load-error", id)}
        message={runtimeQuery.error?.message ?? t("runtimeStateUnknown")}
        onRetry={() => runtimeQuery.refetch()}
      />
    );
  } else {
    pageBody = (
      <div className="flex min-h-0 flex-1 flex-col">
        <div className={focusMode ? "hidden" : "shrink-0"}>
          <SessionHeader
            profile={profile}
            runtime={runtime}
            profiles={profilesQuery.data ?? []}
            groups={groupsQuery.data ?? []}
            audioMuted={session.audioMuted}
            diagnosticsOpen={diagnosticsOpen}
            detailsOpen={detailsOpen}
            focusMode={focusMode}
            onAudioToggle={session.toggleAudio}
            onDiagnosticsToggle={() => setDiagnosticsOpen(!diagnosticsOpen)}
            onDetailsToggle={() => handleDetailsOpenChange(!detailsOpen)}
            onFocusToggle={() => setFocusMode(!focusMode)}
            onStop={() => stopMutation.mutate(id)}
            onApplyRestart={() => applyMutation.mutate(id)}
          />
        </div>
        <div className="flex min-h-0 flex-1">
          <div
            data-testid={SESS_STAGE}
            data-stage={stage}
            className="relative min-w-0 flex-1 overflow-hidden bg-stage"
          >
            <iframe
              key="session-iframe"
              ref={iframeRef}
              data-testid={SESS_IFRAME}
              data-stage={stage}
              src={`/selkies/index.html?profileId=${encodeURIComponent(id)}&_k=${session.reloadKey}`}
              allow="autoplay; fullscreen; clipboard-read; clipboard-write"
              className="absolute inset-0 h-full w-full border-none"
              title={t("sessTitle")}
            />
            {stage === "connected" ? <ClipboardPermissionHint /> : null}
            {setDesiredStateMutation.isError ? (
              <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-center p-md">
                <div className="pointer-events-auto max-w-panel">
                  <Banner tone="danger" testId={sessId("launch", "error")}>
                    {t("sessionStartFailed", {
                      error:
                        setDesiredStateMutation.error instanceof Error
                          ? setDesiredStateMutation.error.message
                          : t("runtimeStateUnknown"),
                    })}
                  </Banner>
                </div>
              </div>
            ) : null}
            {stage !== "connected" ? (
              <SessionStagePanel
                stage={stage}
                diagnostics={diagnosticsView}
                onReconnect={session.reconnect}
                onViewStatus={() => navigate(`/profiles/${id}/config`)}
                onLaunch={() => setDesiredStateMutation.mutate({ id, state: "running" })}
              />
            ) : null}
            {diagnosticsOpen ? (
              <DiagnosticsOverlay
                diagnostics={diagnosticsView}
                onClose={() => setDiagnosticsOpen(false)}
              />
            ) : null}
          </div>
          <div className={focusMode ? "hidden" : "flex"}>
            <SessionDetailsPanel
              profile={profile}
              runtime={runtime}
              groups={groupsQuery.data ?? []}
              proxies={proxiesQuery.data ?? []}
              fontSets={fontSetsQuery.data ?? []}
              open={detailsOpen}
              onOpenChange={handleDetailsOpenChange}
            />
          </div>
        </div>
        {focusMode ? <FocusModeToolbar onExit={() => setFocusMode(false)} /> : null}
      </div>
    );
  }

  return (
    <div data-testid={SESS_PAGE} data-stage={stage} className="flex h-full min-h-0 flex-col bg-background">
      {pageBody}
    </div>
  );
}
