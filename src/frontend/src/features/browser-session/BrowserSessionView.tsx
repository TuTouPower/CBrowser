import React, { useRef, useState } from "react";
import { BrowserSessionViewProps } from "./types";
import { useBrowserSession } from "./useBrowserSession";
import { SessionDiagnostics } from "./SessionDiagnostics";
import { ClipboardPermissionHint } from "./ClipboardPermissionHint";
import { useI18n } from "../../i18n";

export const BrowserSessionView: React.FC<BrowserSessionViewProps> = ({
  profileId,
  clipboardSync = true,
  className = "",
  initialStage,
  diagnostics: overrideDiagnostics,
  errorMessage: overrideError,
  onCheckRuntimeStatus,
  runtimeStatusUrl,
}) => {
  const { t } = useI18n();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [showDiagnosticsOverlay, setShowDiagnosticsOverlay] = useState(false);

  const {
    stage,
    diagnostics,
    errorMessage,
    reloadKey,
    reconnect,
    audioMuted,
    toggleAudio,
  } = useBrowserSession(profileId, iframeRef, {
      initialStage,
      errorMessage: overrideError,
      diagnostics: overrideDiagnostics,
      runtimeStatusUrl,
    });

  const isErrorStage = [
    "runtime_not_ready",
    "signaling_failed",
    "ice_failed",
    "media_no_frames",
    "error",
  ].includes(stage);
  const isBlockingStage = isErrorStage || stage === "stopping";

  const iframeSrc = `/selkies/index.html?profileId=${encodeURIComponent(
    profileId
  )}&_k=${reloadKey}`;

  return (
    <div
      data-testid="browser-session-view"
      data-stage={stage}
      className={`relative w-full h-full bg-neutral-950 overflow-hidden select-none ${className}`}
    >
      {/* Selkies official client iframe */}
      <iframe
        ref={iframeRef}
        data-testid="browser-session-iframe"
        src={iframeSrc}
        title={`Browser Session for profile ${profileId}`}
        allow="autoplay; fullscreen; clipboard-read; clipboard-write"
        className="w-full h-full border-0 absolute inset-0 z-0 bg-neutral-900"
      />

      {/* Connection & Diagnostic Overlay (AC-007) */}
      {(isBlockingStage || showDiagnosticsOverlay) && (
        <SessionDiagnostics
          stage={stage}
          diagnostics={diagnostics}
          errorMessage={errorMessage || undefined}
          onReconnect={stage === "stopping" ? undefined : reconnect}
          onCheckStatus={onCheckRuntimeStatus}
        />
      )}

      {stage === "connected" && clipboardSync && <ClipboardPermissionHint />}

      {/* Per-page audio mute through the official Selkies pipelineControl */}
      {stage === "connected" && (
        <button
          type="button"
          data-testid="session-audio-toggle-btn"
          data-audio-muted={audioMuted ? "true" : "false"}
          aria-pressed={audioMuted}
          aria-label={audioMuted ? t("audioUnmute") : t("audioMute")}
          onClick={toggleAudio}
          className="absolute bottom-2 left-2 z-10 text-xs px-2.5 py-1 bg-neutral-800/80 hover:bg-neutral-700 text-neutral-300 rounded border border-neutral-700/60 backdrop-blur-sm transition-opacity opacity-60 hover:opacity-100"
        >
          {audioMuted ? t("audioUnmute") : t("audioMute")}
        </button>
      )}

      {/* Diagnostics Toggle Button (Top Right Floating) */}
      {stage === "connected" && (
        <button
          type="button"
          data-testid="session-toggle-diag-btn"
          onClick={() => setShowDiagnosticsOverlay((prev) => !prev)}
          className="absolute top-2 right-2 z-10 text-xs px-2.5 py-1 bg-neutral-800/80 hover:bg-neutral-700 text-neutral-300 rounded border border-neutral-700/60 backdrop-blur-sm transition-opacity opacity-40 hover:opacity-100"
          title={t("sessionToggleDiagnostics")}
        >
          {showDiagnosticsOverlay ? t("sessionHideDiagnostics") : t("sessionToggleDiagnostics")}
        </button>
      )}
    </div>
  );
};
