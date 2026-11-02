import React from "react";
import type { AudioStatus } from "./audio_status";
import type { TranslationKey } from "../../i18n";
import { useI18n } from "../../i18n";
import { SessionDiagnosticsData, SessionStage } from "./types";

interface SessionDiagnosticsProps {
  stage: SessionStage;
  diagnostics?: Partial<SessionDiagnosticsData>;
  errorMessage?: string;
  onReconnect?: () => void;
  onCheckStatus?: () => void;
}

const AUDIO_STATUS_KEYS: Record<AudioStatus, TranslationKey> = {
  normal: "audioStatusNormal",
  no_track: "audioStatusNoTrack",
  no_data: "audioStatusNoData",
  unknown: "audioStatusUnknown",
  muted: "audioStatusMuted",
};

const STAGE_TITLE_KEYS: Record<SessionStage, TranslationKey> = {
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
};

export const SessionDiagnostics: React.FC<SessionDiagnosticsProps> = ({
  stage,
  diagnostics,
  errorMessage,
  onReconnect,
  onCheckStatus,
}) => {
  const { t } = useI18n();
  const title = t(STAGE_TITLE_KEYS[stage] ?? "sessionStageCheckingRuntime");
  const isErrorStage = [
    "runtime_not_ready",
    "signaling_failed",
    "web_locks_unavailable",
    "ice_failed",
    "media_no_frames",
    "error",
  ].includes(stage);

  const selectedPair = diagnostics?.selectedPair;
  const rttDisplay =
    diagnostics?.roundTripTime !== undefined
      ? `${diagnostics.roundTripTime} ms`
      : selectedPair?.roundTripTime !== undefined
      ? `${Math.round(selectedPair.roundTripTime * 1000)} ms`
      : null;

  return (
    <div
      data-testid="session-diagnostics-overlay"
      className="absolute inset-0 bg-neutral-900/90 text-white flex flex-col items-center justify-center p-6 z-20 backdrop-blur-sm"
    >
      <div className="max-w-md w-full bg-neutral-800 border border-neutral-700 rounded-lg p-6 shadow-xl space-y-4">
        <div className="flex items-center space-x-3">
          <div
            className={`w-3 h-3 rounded-full ${
              isErrorStage
                ? "bg-red-500 animate-pulse"
                : "bg-amber-400 animate-ping"
            }`}
          />
          <h2
            data-testid="session-stage-title"
            className="text-lg font-semibold tracking-wide"
          >
            {title}
          </h2>
        </div>

        {errorMessage && (
          <p
            data-testid="session-error-message"
            className="text-sm text-red-300 bg-red-950/50 border border-red-800/60 rounded p-2.5 break-words"
          >
            {errorMessage}
          </p>
        )}

        {/* Diagnostic Metrics Display */}
        <div className="text-xs bg-neutral-950 border border-neutral-800 rounded p-3 space-y-1.5 font-mono text-neutral-300">
          <div className="flex justify-between">
            <span className="text-neutral-400">{t("sessionDiagConnectionState")}:</span>
            <span data-testid="diag-conn-state">
              {diagnostics?.connectionState || "n/a"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-neutral-400">{t("sessionDiagIceState")}:</span>
            <span data-testid="diag-ice-state">
              {diagnostics?.iceConnectionState || "n/a"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-neutral-400">{t("sessionDiagSignalingState")}:</span>
            <span data-testid="diag-sig-state">
              {diagnostics?.signalingState || "n/a"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-neutral-400">{t("sessionDiagAudioStatus")}:</span>
            <span data-testid="diag-audio-status">
              {t(AUDIO_STATUS_KEYS[diagnostics?.audioStatus || "unknown"])}
            </span>
          </div>
          {rttDisplay && (
            <div className="flex justify-between">
              <span className="text-neutral-400">{t("sessionDiagRoundTripTime")}:</span>
              <span data-testid="diag-rtt">{rttDisplay}</span>
            </div>
          )}
          {diagnostics?.packetsLost !== undefined && (
            <div className="flex justify-between">
              <span className="text-neutral-400">{t("sessionDiagPacketsLost")}:</span>
              <span data-testid="diag-packets-lost">
                {diagnostics.packetsLost}
              </span>
            </div>
          )}
          {diagnostics?.packetsReceived !== undefined && (
            <div className="flex justify-between">
              <span className="text-neutral-400">{t("sessionDiagPacketsReceived")}:</span>
              <span data-testid="diag-packets-received">
                {diagnostics.packetsReceived}
              </span>
            </div>
          )}
          {diagnostics?.framesDecoded !== undefined && (
            <div className="flex justify-between">
              <span className="text-neutral-400">{t("sessionDiagFramesDecoded")}:</span>
              <span data-testid="diag-frames-decoded">
                {diagnostics.framesDecoded}
              </span>
            </div>
          )}
          {selectedPair && (
            <div className="pt-1.5 border-t border-neutral-800 space-y-1">
              <div className="flex justify-between">
                <span className="text-neutral-400">{t("sessionDiagCandidateType")}:</span>
                <span data-testid="diag-candidate-type">
                  {selectedPair.localType || "unknown"} →{" "}
                  {selectedPair.remoteType || "unknown"}
                </span>
              </div>
              {selectedPair.remoteAddress && (
                <div className="flex justify-between">
                  <span className="text-neutral-400">{t("sessionDiagRemoteEndpoint")}:</span>
                  <span data-testid="diag-candidate-address">
                    {selectedPair.remoteAddress}:{selectedPair.remotePort}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center space-x-3 pt-2">
          {onReconnect && (
            <button
              type="button"
              data-testid="session-reconnect-btn"
              onClick={onReconnect}
              className="flex-1 bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white font-medium py-2 px-4 rounded text-sm transition-colors text-center"
            >
              {t("sessionReconnect")}
            </button>
          )}
          {onCheckStatus && (
            <button
              type="button"
              data-testid="session-view-status-btn"
              onClick={onCheckStatus}
              className="flex-1 bg-neutral-700 hover:bg-neutral-600 active:bg-neutral-800 text-neutral-200 font-medium py-2 px-4 rounded text-sm transition-colors text-center"
            >
              {t("sessionViewStatus")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
