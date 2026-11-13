import { useSyncExternalStore } from "react";
import type { JSX } from "react";
import { useI18n } from "../../i18n";
import { Banner, Button, MonoValue } from "../../shared/ui";
import { SessionDiagnosticsSource } from "./diagnostics_source";
import { sessId } from "./session_keys";
import type { SessionDiagnosticsData } from "./types";

export interface DiagnosticsOverlayProps {
  diagnostics: SessionDiagnosticsData;
  source: SessionDiagnosticsSource;
  onClose: () => void;
}

export function DiagnosticsOverlay({
  diagnostics,
  source,
  onClose,
}: DiagnosticsOverlayProps): JSX.Element {
  const { t } = useI18n();
  const snapshot = useSyncExternalStore(source.subscribe, source.getSnapshot);
  const connection = snapshot.connection;
  const sample = snapshot.diagnostics;

  const audioLabels: Record<string, string> = {
    normal: t("audioStatusNormal"),
    no_track: t("audioStatusNoTrack"),
    no_data: t("audioStatusNoData"),
    unknown: t("audioStatusUnknown"),
    muted: t("audioStatusMuted"),
  };
  const audioStatusValue = sample.audioStatus;
  const audioStatus = audioStatusValue
    ? audioLabels[audioStatusValue] ?? audioStatusValue
    : "-";
  const rows: Array<{
    label: string;
    value: string | number;
    testId: string;
  }> = [
    { label: t("sessionDiagConnectionState"), value: connection.connectionState ?? "-", testId: sessId("diag", "conn-state") },
    { label: t("sessionDiagIceState"), value: connection.iceConnectionState ?? "-", testId: sessId("diag", "ice-state") },
    { label: t("sessionDiagSignalingState"), value: connection.signalingState ?? "-", testId: sessId("diag", "signaling-state") },
    { label: t("sessionDiagAudioStatus"), value: audioStatus, testId: sessId("diag", "audio-status") },
    { label: t("sessionDiagFramesDecoded"), value: sample.framesDecoded ?? "-", testId: sessId("diag", "frames-decoded") },
    { label: t("sessionDiagPacketsLost"), value: sample.packetsLost ?? "-", testId: sessId("diag", "packets-lost") },
    { label: t("sessionDiagRoundTripTime"), value: sample.roundTripTime ?? "-", testId: sessId("diag", "round-trip-time") },
  ];
  return (
    <div
      data-testid={sessId("diag", "overlay")}
      className="pointer-events-none absolute inset-none flex justify-end p-md"
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
