import { useState, useEffect, useCallback, useRef } from "react";
import {
  AUDIO_STATUS_WINDOW_MS,
  deriveAudioStatus,
  type AudioStatsSample,
} from "./audio_status";
import { sendAudioPipelineControl } from "./audio_control";
import { SessionDiagnosticsData, SessionStage } from "./types";
import { useI18n } from "../../i18n";
import { ApiClient, ApiError, defaultApiClient } from "../../shared/api/client";

interface UseBrowserSessionOptions {
  initialStage?: SessionStage;
  errorMessage?: string;
  diagnostics?: Partial<SessionDiagnosticsData>;
  apiClient?: ApiClient;
  mediaTimeoutMs?: number;
  iceDisconnectGraceMs?: number;
  transportRecoveryWindowMs?: number;
}

// WebRTC "disconnected" often self-heals; only a persistent one is a failure.
const DEFAULT_ICE_DISCONNECT_GRACE_MS = 5000;
// t026 AC-011: a first-connection signaling drop while the transport
// layer reports "recovering" is presented as recovery, and only an
// explicit transport failure or an exhausted window is a failure.
const DEFAULT_TRANSPORT_RECOVERY_WINDOW_MS = 30000;
const TRANSPORT_RECOVERY_POLL_MS = 2000;

// A diagnostic/terminal stage means the runtime is not running (or the
// session has ended), so the host has already rendered its recovery UI.
// The iframe client can still open and close a signaling WebSocket after
// that: Selkies 2.2.1 defers initialization until its own core module
// loads, which under load happens after the host settles on the diagnostic
// stage.  Such transport events are expected fallout, not a live-session
// disconnect, and must not drag the stage back to "reconnecting" (which
// unmounts the diagnostic overlay and its reconnect/status actions).
const DIAGNOSTIC_STAGES: SessionStage[] = [
  "runtime_not_ready",
  "signaling_failed",
  "web_locks_unavailable",
  "ice_failed",
  "media_no_frames",
  "error",
  "stopping",
];

export function useBrowserSession(
  profileId: string,
  iframeRef: React.RefObject<HTMLIFrameElement | null>,
  options: UseBrowserSessionOptions = {}
) {
  const { t } = useI18n();
  // Effects always read the latest translator through this ref. Depending
  // on the t function identity instead would re-run the runtime check (and
  // reset an already connected session) whenever the language changes (A17).
  const tRef = useRef(t);
  tRef.current = t;
  const [stage, setStage] = useState<SessionStage>(
    options.initialStage || "checking_runtime"
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(
    options.errorMessage || null
  );
  const [reloadKey, setReloadKey] = useState<number>(0);
  const [audioMuted, setAudioMuted] = useState<boolean>(false);
  const [diagData, setDiagData] = useState<SessionDiagnosticsData>({
    stage: options.initialStage || "checking_runtime",
    profileId,
    ...options.diagnostics,
  });

  const mediaTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const statsPollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const wsCloseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const iceDisconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const transportRecoveryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null
  );
  const apiClientRef = useRef<ApiClient>(options.apiClient || defaultApiClient);
  apiClientRef.current = options.apiClient || defaultApiClient;
  const mountedRef = useRef<boolean>(true);
  const audioMutedRef = useRef<boolean>(false);
  const audioSamplesRef = useRef<AudioStatsSample[]>([]);
  const stageRef = useRef<SessionStage>(
    options.initialStage || "checking_runtime"
  );
  const wasConnectedRef = useRef<boolean>(
    (options.initialStage || "checking_runtime") === "connected"
  );
  const webLocksUnavailableRef = useRef<boolean>(false);

  // Sync prop changes
  useEffect(() => {
    if (options.initialStage) {
      setStage(options.initialStage);
    }
  }, [options.initialStage]);

  useEffect(() => {
    if (options.errorMessage !== undefined) {
      setErrorMessage(options.errorMessage);
    }
  }, [options.errorMessage]);

  useEffect(() => {
    if (options.diagnostics) {
      setDiagData((prev) => ({
        ...prev,
        ...options.diagnostics,
      }));
    }
  }, [options.diagnostics]);

  useEffect(() => {
    audioMutedRef.current = audioMuted;
  }, [audioMuted]);

  useEffect(() => {
    stageRef.current = stage;
    if (stage === "connected") {
      wasConnectedRef.current = true;
    }
  }, [stage]);

  const applyAudioState = useCallback(
    (enabled: boolean) => {
      const win = iframeRef.current?.contentWindow;
      if (!win) return;
      sendAudioPipelineControl(win, window.location.origin, enabled);
    },
    [iframeRef]
  );

  const toggleAudio = useCallback(() => {
    const nextMuted = !audioMutedRef.current;
    audioMutedRef.current = nextMuted;
    setAudioMuted(nextMuted);
    applyAudioState(!nextMuted);
  }, [applyAudioState]);

  // Reconnect action
  const reconnect = useCallback(() => {
    if (mediaTimerRef.current) clearTimeout(mediaTimerRef.current);
    if (statsPollTimerRef.current) clearInterval(statsPollTimerRef.current);
    if (wsCloseTimerRef.current) clearTimeout(wsCloseTimerRef.current);
    if (iceDisconnectTimerRef.current) clearTimeout(iceDisconnectTimerRef.current);
    if (transportRecoveryTimerRef.current)
      clearTimeout(transportRecoveryTimerRef.current);

    setErrorMessage(null);
    webLocksUnavailableRef.current = false;
    setStage("reconnecting");
    setReloadKey((k) => k + 1);
    audioSamplesRef.current = [];
  }, []);

  const failSignaling = useCallback((code: number) => {
    setStage("signaling_failed");
    setErrorMessage(tRef.current("signalingDisconnected", { code }));
  }, []);

  // First-connection signaling drop (t026 AC-011): while the transport
  // layer is recovering, present recovery and poll within a bounded
  // window; only an explicit transport failure or the window expiring
  // turns this into signaling_failed.
  const handleInitialSignalingClose = useCallback(
    (code: number) => {
      const windowMs =
        options.transportRecoveryWindowMs ??
        DEFAULT_TRANSPORT_RECOVERY_WINDOW_MS;
      const deadline = Date.now() + windowMs;
      setStage("reconnecting");
      const poll = async (): Promise<void> => {
        if (!mountedRef.current) return;
        let transportState: string | undefined;
        try {
          const data = await apiClientRef.current.profiles.getRuntime(profileId);
          transportState = data.transport?.transport_state ?? undefined;
        } catch {
          transportState = undefined;
        }
        if (!mountedRef.current) return;
        if (transportState === "ready") {
          reconnect();
          return;
        }
        if (transportState === "failed" || Date.now() >= deadline) {
          failSignaling(code);
          return;
        }
        transportRecoveryTimerRef.current = setTimeout(() => {
          void poll();
        }, TRANSPORT_RECOVERY_POLL_MS);
      };
      void poll();
    },
    [profileId, reconnect, failSignaling, options.transportRecoveryWindowMs]
  );

  // Check runtime status on mount if not provided with explicit initialStage
  useEffect(() => {
    mountedRef.current = true;
    if (options.initialStage) {
      return;
    }

    let active = true;
    const client = options.apiClient || defaultApiClient;
    const checkRuntime = async () => {
      try {
        const data = await client.profiles.getRuntime(profileId);
        if (!active) return;
        const observed = data.observed_state;
        if (observed === "stopping") {
          setStage("stopping");
          setErrorMessage(null);
        } else if (observed === "error") {
          setStage("error");
          setErrorMessage(
            tRef.current("runtimeReportedError", {
              state: observed || tRef.current("runtimeStateUnknown"),
            })
          );
        } else if (observed !== "running") {
          setStage("runtime_not_ready");
          setErrorMessage(
            tRef.current("runtimeNotRunning", {
              state: observed || tRef.current("runtimeStateUnknown"),
            })
          );
        } else {
          setStage("connecting_signaling");
        }
      } catch (err) {
        if (!active) return;
        if (err instanceof ApiError && err.status === 401) {
          // The auth provider handles the redirect to login.
          return;
        }
        const reason =
          err instanceof ApiError
            ? `${err.status} ${err.message}`
            : err instanceof Error && err.message
              ? err.message
              : tRef.current("runtimeStateUnknown");
        setStage("runtime_not_ready");
        setErrorMessage(tRef.current("runtimeCheckUnavailable", { reason }));
      }
    };

    checkRuntime();
    return () => {
      active = false;
      mountedRef.current = false;
    };
  }, [
    profileId,
    options.apiClient,
    options.initialStage,
    reloadKey,
  ]);

  // Handle postMessage events from iframe adapter
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const iframeWindow = iframeRef.current?.contentWindow;
      if (!iframeWindow) return;
      if (event.source !== iframeWindow) return;
      if (event.origin !== window.location.origin) return;
      if (!event.data || typeof event.data !== "object") return;
      const { type, connectionState, iceConnectionState, signalingState, code } =
        event.data;

      if (
        DIAGNOSTIC_STAGES.includes(stageRef.current) &&
        (type === "CBROWSER_WS_CLOSE" ||
          type === "CBROWSER_PC_STATE" ||
          type === "CBROWSER_LIFECYCLE_STALE")
      ) {
        return;
      }

      if (type === "CBROWSER_PC_STATE") {
        setDiagData((prev) => ({
          ...prev,
          connectionState,
          iceConnectionState,
          signalingState,
        }));

        const disconnected =
          iceConnectionState === "disconnected" ||
          connectionState === "disconnected";
        if (!disconnected && iceDisconnectTimerRef.current) {
          clearTimeout(iceDisconnectTimerRef.current);
          iceDisconnectTimerRef.current = null;
        }

        if (
          iceConnectionState === "failed" ||
          connectionState === "failed"
        ) {
          if (iceDisconnectTimerRef.current) {
            clearTimeout(iceDisconnectTimerRef.current);
            iceDisconnectTimerRef.current = null;
          }
          setStage("ice_failed");
          setErrorMessage(tRef.current("iceConnectivityCheckFailed"));
        } else if (disconnected) {
          if (!iceDisconnectTimerRef.current) {
            iceDisconnectTimerRef.current = setTimeout(() => {
              iceDisconnectTimerRef.current = null;
              setStage("ice_failed");
              setErrorMessage(tRef.current("iceConnectivityLost"));
            }, options.iceDisconnectGraceMs ?? DEFAULT_ICE_DISCONNECT_GRACE_MS);
          }
        } else if (
          connectionState === "connected" ||
          iceConnectionState === "connected"
        ) {
          setStage((prev) => (prev !== "connected" ? "media_waiting" : prev));
        }
      } else if (type === "CBROWSER_WEB_LOCKS_UNAVAILABLE") {
        webLocksUnavailableRef.current = true;
        setStage("web_locks_unavailable");
        setErrorMessage(tRef.current("webLocksUnavailable"));
      } else if (type === "CBROWSER_WS_CLOSE") {
        if (webLocksUnavailableRef.current) {
          return;
        }
        if (code && code !== 1000) {
          if (wasConnectedRef.current) {
            // Give the official client a chance to resume the session with its
            // existing resume_key; rebuild the iframe only if it stays broken.
            setStage("reconnecting");
            if (wsCloseTimerRef.current) clearTimeout(wsCloseTimerRef.current);
            wsCloseTimerRef.current = setTimeout(async () => {
              const win = iframeRef.current?.contentWindow as any;
              let healthy = false;
              if (win && typeof win.__getWebRTCStats === "function") {
                try {
                  const stats = await win.__getWebRTCStats();
                  healthy = Boolean(stats && stats.connected);
                } catch {
                  healthy = false;
                }
              }
              if (!healthy) {
                reconnect();
              }
            }, 5000);
          } else {
            handleInitialSignalingClose(code);
          }
        }
      } else if (type === "CBROWSER_LIFECYCLE_STALE") {
        const current = stageRef.current;
        if (current !== "reconnecting" && current !== "connecting_signaling") {
          reconnect();
        }
      }
    };

    window.addEventListener("message", handleMessage);
    return () => {
      window.removeEventListener("message", handleMessage);
    };
  }, [
    reconnect,
    iframeRef,
    options.iceDisconnectGraceMs,
    handleInitialSignalingClose,
  ]);

  // Once the session is live, align the official audio pipeline with this page's
  // own mute state (START_AUDIO/STOP_AUDIO), never with another page.
  useEffect(() => {
    if (stage === "connected") {
      applyAudioState(!audioMutedRef.current);
    }
  }, [stage, applyAudioState]);

  // Poll WebRTC stats from iframe window
  useEffect(() => {
    if (
      stage === "runtime_not_ready" ||
      stage === "signaling_failed" ||
      stage === "web_locks_unavailable" ||
      stage === "stopping" ||
      stage === "error"
    ) {
      return;
    }

    const pollStats = async () => {
      const win = iframeRef.current?.contentWindow as any;
      if (!win || typeof win.__getWebRTCStats !== "function") return;

      try {
        const stats = await win.__getWebRTCStats();
        if (!stats) return;

        const now = Date.now();
        const audioSample: AudioStatsSample = {
          at: now,
          present: !!stats.audio,
          bytesReceived: stats.audio?.bytesReceived ?? 0,
          packetsReceived: stats.audio?.packetsReceived ?? 0,
          totalAudioEnergy: stats.audio?.totalAudioEnergy ?? 0,
        };
        const audioHistory = [...audioSamplesRef.current, audioSample].filter(
          (sample) => now - sample.at <= AUDIO_STATUS_WINDOW_MS * 2
        );
        audioSamplesRef.current = audioHistory;
        const audioStatus = deriveAudioStatus(
          audioHistory,
          now,
          AUDIO_STATUS_WINDOW_MS,
          audioMutedRef.current
        );

        setDiagData((prev) => ({
          ...prev,
          connectionState: stats.connectionState || prev.connectionState,
          iceConnectionState:
            stats.iceConnectionState || prev.iceConnectionState,
          signalingState: stats.signalingState || prev.signalingState,
          selectedPair: stats.pair || prev.selectedPair,
          framesDecoded: stats.video?.framesDecoded ?? prev.framesDecoded,
          keyFramesDecoded:
            stats.video?.keyFramesDecoded ?? prev.keyFramesDecoded,
          packetsLost: stats.video?.packetsLost ?? prev.packetsLost,
          packetsReceived:
            stats.video?.packetsReceived ?? prev.packetsReceived,
          roundTripTime: stats.pair?.roundTripTime
            ? Math.round(stats.pair.roundTripTime * 1000)
            : prev.roundTripTime,
          totalAudioEnergy: stats.audio?.totalAudioEnergy ?? prev.totalAudioEnergy,
          audioBytesReceived:
            stats.audio?.bytesReceived ?? prev.audioBytesReceived,
          audioStatus,
        }));

        if (stats.video && stats.video.framesDecoded > 0) {
          setStage("connected");
          if (mediaTimerRef.current) {
            clearTimeout(mediaTimerRef.current);
            mediaTimerRef.current = null;
          }
        }
      } catch {
        // Ignored in cross-origin or unloaded cases
      }
    };

    statsPollTimerRef.current = setInterval(pollStats, 1000);
    return () => {
      if (statsPollTimerRef.current) {
        clearInterval(statsPollTimerRef.current);
      }
    };
  }, [stage, iframeRef]);

  // Media frames timeout check (AC-007)
  useEffect(() => {
    if (stage === "media_waiting") {
      const timeoutMs = options.mediaTimeoutMs || 10000;
      mediaTimerRef.current = setTimeout(() => {
        if (mountedRef.current) {
          setStage((curr) =>
            curr === "media_waiting" ? "media_no_frames" : curr
          );
          setErrorMessage(tRef.current("mediaFramesTimeout"));
        }
      }, timeoutMs);

      return () => {
        if (mediaTimerRef.current) {
          clearTimeout(mediaTimerRef.current);
        }
      };
    }
  }, [stage, options.mediaTimeoutMs]);

  // Page Lifecycle & bfcache reactivation (AC-007)
  useEffect(() => {
    const handleHostReactivate = () => {
      const win = iframeRef.current?.contentWindow as any;
      if (win && typeof win.__getWebRTCStats === "function") {
        win
          .__getWebRTCStats()
          .then((s: any) => {
            if (!s || !s.connected) {
              reconnect();
            }
          })
          .catch(() => reconnect());
      }
    };

    document.addEventListener("resume", handleHostReactivate);
    const handlePageShow = (event: PageTransitionEvent) => {
      if (event.persisted) handleHostReactivate();
    };
    window.addEventListener("pageshow", handlePageShow);

    return () => {
      document.removeEventListener("resume", handleHostReactivate);
      window.removeEventListener("pageshow", handlePageShow);
    };
  }, [reconnect, iframeRef]);

  // AC-003: On unmount, only clean up timers and release iframe reference.
  // NEVER call profile stop API or desired-state PATCH.
  useEffect(() => {
    return () => {
      if (mediaTimerRef.current) clearTimeout(mediaTimerRef.current);
      if (statsPollTimerRef.current) clearInterval(statsPollTimerRef.current);
      if (wsCloseTimerRef.current) clearTimeout(wsCloseTimerRef.current);
      if (iceDisconnectTimerRef.current) clearTimeout(iceDisconnectTimerRef.current);
      if (iframeRef.current) {
        iframeRef.current.src = "about:blank";
      }
    };
  }, [iframeRef]);

  return {
    stage,
    diagnostics: diagData,
    errorMessage,
    reloadKey,
    reconnect,
    audioMuted,
    toggleAudio,
  };
}
