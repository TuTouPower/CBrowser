import { useState, useEffect, useCallback, useRef } from "react";
import { sendAudioPipelineControl } from "./audio_control";
import {
  SessionDiagnosticsData,
  SessionStage,
  type SelkiesIframeWindow,
  type SelkiesStats,
} from "./types";
import {
  deriveSessionStage,
  isTerminalStage,
  type RuntimeObservedState,
} from "./session_stage";
import {
  SessionDiagnosticsSource,
  type ConnectionSnapshot,
} from "./diagnostics_source";
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
  runtimeState?: RuntimeObservedState | null;
}

// WebRTC "disconnected" often self-heals; only a persistent one is a failure.
const DEFAULT_ICE_DISCONNECT_GRACE_MS = 5000;
// t026 AC-011: a first-connection signaling drop while the transport
// layer reports "recovering" is presented as recovery, and only an
// explicit transport failure or an exhausted window is a failure.
const DEFAULT_TRANSPORT_RECOVERY_WINDOW_MS = 30000;
const TRANSPORT_RECOVERY_POLL_MS = 2000;

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
  const wsCloseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const iceDisconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const transportRecoveryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null
  );
  const apiClientRef = useRef<ApiClient>(options.apiClient || defaultApiClient);
  apiClientRef.current = options.apiClient || defaultApiClient;
  const mountedRef = useRef<boolean>(true);
  const audioMutedRef = useRef<boolean>(false);
  const stageRef = useRef<SessionStage>(
    options.initialStage || "checking_runtime"
  );
  const wasConnectedRef = useRef<boolean>(
    (options.initialStage || "checking_runtime") === "connected"
  );
  const webLocksUnavailableRef = useRef<boolean>(false);
  const generationRef = useRef<number>(0);
  const lastGenerationKeyRef = useRef<string>("");

  const generationKey = `${profileId}:${reloadKey}`;
  if (lastGenerationKeyRef.current !== generationKey) {
    lastGenerationKeyRef.current = generationKey;
    generationRef.current += 1;
  }
  const generation = generationRef.current;

  const effectiveStage = deriveSessionStage(stage, options.runtimeState);
  const effectiveStageRef = useRef<SessionStage>(effectiveStage);
  effectiveStageRef.current = effectiveStage;

  const isCurrent = useCallback(
    (gen: number): boolean =>
      mountedRef.current && gen === generationRef.current,
    []
  );

  const clearTimer = useCallback(
    (ref: React.MutableRefObject<ReturnType<typeof setTimeout> | null>) => {
      if (ref.current !== null) {
        clearTimeout(ref.current);
        ref.current = null;
      }
    },
    []
  );

  const clearAllTimers = useCallback(() => {
    clearTimer(mediaTimerRef);
    clearTimer(wsCloseTimerRef);
    clearTimer(iceDisconnectTimerRef);
    clearTimer(transportRecoveryTimerRef);
  }, [clearTimer]);

  const readStats = useCallback(async (): Promise<SelkiesStats | null> => {
    const win = iframeRef.current?.contentWindow as
      | SelkiesIframeWindow
      | null
      | undefined;
    if (!win || typeof win.__getWebRTCStats !== "function") return null;
    try {
      return await win.__getWebRTCStats();
    } catch {
      return null;
    }
  }, [iframeRef]);

  const handleConnectionSignal = useCallback(
    (connection: ConnectionSnapshot) => {
      const gen = generationRef.current;
      if (!isCurrent(gen)) return;
      setDiagData((prev) => {
        const connectionState = connection.connectionState ?? prev.connectionState;
        const iceConnectionState =
          connection.iceConnectionState ?? prev.iceConnectionState;
        const signalingState =
          connection.signalingState ?? prev.signalingState;
        if (
          prev.connectionState === connectionState &&
          prev.iceConnectionState === iceConnectionState &&
          prev.signalingState === signalingState
        ) {
          return prev;
        }
        return { ...prev, connectionState, iceConnectionState, signalingState };
      });
      if (
        connection.hasFrames &&
        stageRef.current !== "connected" &&
        !isTerminalStage(effectiveStageRef.current)
      ) {
        setStage("connected");
        clearTimer(mediaTimerRef);
      }
    },
    [isCurrent, clearTimer]
  );

  const sourceRef = useRef<SessionDiagnosticsSource | null>(null);
  if (sourceRef.current === null) {
    sourceRef.current = new SessionDiagnosticsSource({
      readStats,
      onConnectionSignal: handleConnectionSignal,
    });
  }
  const diagnosticsSource = sourceRef.current;

  useEffect(() => {
    diagnosticsSource.setGeneration(generation);
  }, [diagnosticsSource, generation]);

  useEffect(() => {
    diagnosticsSource.setActive(!isTerminalStage(effectiveStage));
  }, [diagnosticsSource, effectiveStage, generation]);

  useEffect(() => {
    diagnosticsSource.setMuted(audioMuted);
  }, [diagnosticsSource, audioMuted]);

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

  useEffect(() => {
    if (isTerminalStage(effectiveStage)) {
      clearTimer(mediaTimerRef);
      clearTimer(wsCloseTimerRef);
      clearTimer(iceDisconnectTimerRef);
      clearTimer(transportRecoveryTimerRef);
    }
  }, [effectiveStage, generation, clearTimer]);

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

  const reconnect = useCallback(() => {
    clearAllTimers();
    setErrorMessage(null);
    webLocksUnavailableRef.current = false;
    setStage("reconnecting");
    setReloadKey((k) => k + 1);
  }, [clearAllTimers]);

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
      const gen = generationRef.current;
      const windowMs =
        options.transportRecoveryWindowMs ??
        DEFAULT_TRANSPORT_RECOVERY_WINDOW_MS;
      const deadline = Date.now() + windowMs;
      setStage("reconnecting");
      const poll = async (): Promise<void> => {
        if (!isCurrent(gen)) return;
        let transportState: string | undefined;
        try {
          const data = await apiClientRef.current.profiles.getRuntime(profileId);
          transportState = data.transport?.transport_state ?? undefined;
        } catch {
          transportState = undefined;
        }
        if (!isCurrent(gen)) return;
        if (transportState === "ready") {
          reconnect();
          return;
        }
        if (transportState === "failed" || Date.now() >= deadline) {
          failSignaling(code);
          return;
        }
        transportRecoveryTimerRef.current = setTimeout(() => {
          transportRecoveryTimerRef.current = null;
          void poll();
        }, TRANSPORT_RECOVERY_POLL_MS);
      };
      void poll();
    },
    [
      profileId,
      reconnect,
      failSignaling,
      options.transportRecoveryWindowMs,
      isCurrent,
    ]
  );

  // Check runtime status on mount if not provided with explicit initialStage
  useEffect(() => {
    const gen = generationRef.current;
    const client = options.apiClient || defaultApiClient;
    const checkRuntime = async () => {
      try {
        const data = await client.profiles.getRuntime(profileId);
        if (!isCurrent(gen)) return;
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
        if (!isCurrent(gen)) return;
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

    if (!options.initialStage) {
      void checkRuntime();
    }
  }, [profileId, options.apiClient, options.initialStage, reloadKey, isCurrent]);

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
      const gen = generationRef.current;

      // CBROWSER_WS_CLOSE / CBROWSER_PC_STATE are expected transport fallout
      // on a diagnostic stage. CBROWSER_LIFECYCLE_STALE is an explicit
      // rebuild request after a broken PeerConnection and must reconnect
      // even while the recovery UI is shown.
      if (
        isTerminalStage(effectiveStageRef.current) &&
        (type === "CBROWSER_WS_CLOSE" || type === "CBROWSER_PC_STATE")
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
              if (!isCurrent(gen)) return;
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
              wsCloseTimerRef.current = null;
              const win = iframeRef.current?.contentWindow as
                | SelkiesIframeWindow
                | null
                | undefined;
              let healthy = false;
              if (win && typeof win.__getWebRTCStats === "function") {
                const stats = await readStats();
                if (!isCurrent(gen)) return;
                healthy = Boolean(stats && stats.connected);
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
    readStats,
    isCurrent,
  ]);

  // Once the session is live, align the official audio pipeline with this page's
  // own mute state (START_AUDIO/STOP_AUDIO), never with another page.
  useEffect(() => {
    if (stage === "connected") {
      applyAudioState(!audioMutedRef.current);
    }
  }, [stage, applyAudioState]);

  // Media frames timeout check (AC-007)
  useEffect(() => {
    if (stage === "media_waiting") {
      const gen = generationRef.current;
      const timeoutMs = options.mediaTimeoutMs || 10000;
      mediaTimerRef.current = setTimeout(() => {
        mediaTimerRef.current = null;
        if (!isCurrent(gen)) return;
        setStage((curr) =>
          curr === "media_waiting" ? "media_no_frames" : curr
        );
        setErrorMessage(tRef.current("mediaFramesTimeout"));
      }, timeoutMs);

      return () => {
        clearTimer(mediaTimerRef);
      };
    }
  }, [stage, options.mediaTimeoutMs, isCurrent, clearTimer]);

  // Page Lifecycle & bfcache reactivation (AC-007)
  useEffect(() => {
    const handleHostReactivate = () => {
      const win = iframeRef.current?.contentWindow as
        | SelkiesIframeWindow
        | null
        | undefined;
      if (win && typeof win.__getWebRTCStats === "function") {
        const gen = generationRef.current;
        readStats()
          .then((stats) => {
            if (!isCurrent(gen)) return;
            if (!stats || !stats.connected) {
              reconnect();
            }
          })
          .catch(() => {
            if (isCurrent(gen)) reconnect();
          });
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
  }, [reconnect, iframeRef, readStats, isCurrent]);

  // AC-003: On unmount, only clean up timers and release iframe reference.
  // NEVER call profile stop API or desired-state PATCH.
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearAllTimers();
      diagnosticsSource.dispose();
      if (iframeRef.current) {
        iframeRef.current.src = "about:blank";
      }
    };
  }, [iframeRef, clearAllTimers, diagnosticsSource]);

  return {
    stage,
    diagnostics: diagData,
    errorMessage,
    reloadKey,
    reconnect,
    audioMuted,
    toggleAudio,
    generation,
    diagnosticsSource,
  };
}
