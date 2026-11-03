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
}

// WebRTC "disconnected" often self-heals; only a persistent one is a failure.
const DEFAULT_ICE_DISCONNECT_GRACE_MS = 5000;

export function useBrowserSession(
  profileId: string,
  iframeRef: React.RefObject<HTMLIFrameElement | null>,
  options: UseBrowserSessionOptions = {}
) {
  const { t } = useI18n();
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

    setErrorMessage(null);
    webLocksUnavailableRef.current = false;
    setStage("reconnecting");
    setReloadKey((k) => k + 1);
    audioSamplesRef.current = [];
  }, []);

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
            t("runtimeReportedError", {
              state: observed || t("runtimeStateUnknown"),
            })
          );
        } else if (observed !== "running") {
          setStage("runtime_not_ready");
          setErrorMessage(
            t("runtimeNotRunning", {
              state: observed || t("runtimeStateUnknown"),
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
              : t("runtimeStateUnknown");
        setStage("runtime_not_ready");
        setErrorMessage(t("runtimeCheckUnavailable", { reason }));
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
    t,
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
          setErrorMessage(t("iceConnectivityCheckFailed"));
        } else if (disconnected) {
          if (!iceDisconnectTimerRef.current) {
            iceDisconnectTimerRef.current = setTimeout(() => {
              iceDisconnectTimerRef.current = null;
              setStage("ice_failed");
              setErrorMessage(t("iceConnectivityLost"));
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
        setErrorMessage(t("webLocksUnavailable"));
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
            setStage("signaling_failed");
            setErrorMessage(t("signalingDisconnected", { code }));
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
  }, [reconnect, iframeRef, options.iceDisconnectGraceMs, t]);

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
          setErrorMessage(t("mediaFramesTimeout"));
        }
      }, timeoutMs);

      return () => {
        if (mediaTimerRef.current) {
          clearTimeout(mediaTimerRef.current);
        }
      };
    }
  }, [stage, options.mediaTimeoutMs, t]);

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
