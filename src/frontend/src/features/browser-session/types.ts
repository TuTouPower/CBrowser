/**
 * Type definitions for BrowserSession feature.
 */

import type { AudioStatus } from "./audio_status";
import type { ApiClient } from "../../shared/api/client";

export type { AudioStatus };

export type SessionStage =
  | "checking_runtime"
  | "runtime_not_ready"
  | "stopping"
  | "connecting_signaling"
  | "signaling_failed"
  | "web_locks_unavailable"
  | "ice_failed"
  | "media_waiting"
  | "media_no_frames"
  | "connected"
  | "reconnecting"
  | "error";

export interface CandidatePairDiagnostics {
  localType: string | null;
  remoteType: string | null;
  remoteAddress: string | null;
  remotePort: number | null;
  remoteUfrag: string | null;
  roundTripTime: number; // in seconds or ms
  bytesReceived: number;
}

export interface SessionDiagnosticsData {
  stage: SessionStage;
  profileId: string;
  connectionState?: string;
  iceConnectionState?: string;
  signalingState?: string;
  selectedPair?: CandidatePairDiagnostics | null;
  packetsLost?: number;
  packetsReceived?: number;
  framesDecoded?: number;
  keyFramesDecoded?: number;
  roundTripTime?: number; // formatted or ms
  totalAudioEnergy?: number;
  audioBytesReceived?: number;
  audioStatus?: AudioStatus;
  errorMessage?: string;
  lastUpdated?: string;
}

export interface BrowserSessionViewProps {
  profileId: string;
  clipboardSync?: boolean;
  className?: string;
  initialStage?: SessionStage;
  diagnostics?: Partial<SessionDiagnosticsData>;
  errorMessage?: string;
  onCheckRuntimeStatus?: () => void;
  apiClient?: ApiClient;
}
