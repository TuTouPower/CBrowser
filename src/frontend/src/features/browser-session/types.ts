/**
 * Type definitions for BrowserSession feature.
 */

import type { AudioStatus } from "./audio_status";

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

export interface SelkiesVideoStats {
  framesDecoded: number;
  keyFramesDecoded: number;
  bytesReceived: number;
  packetsLost: number;
  packetsReceived: number;
}

export interface SelkiesAudioStats {
  totalAudioEnergy: number;
  bytesReceived: number;
  packetsReceived: number;
  packetsLost: number;
  trackIdentifier: string | null;
}

export interface SelkiesCandidatePairStats {
  localType: string | null;
  remoteType: string | null;
  remoteAddress: string | null;
  remotePort: number | null;
  remoteUfrag: string | null;
  roundTripTime: number;
  bytesReceived: number;
}

export interface SelkiesStats {
  video: SelkiesVideoStats | null;
  audio: SelkiesAudioStats | null;
  pair: SelkiesCandidatePairStats | null;
  tab_id: string | null;
  connected: boolean;
  connectionState: string;
  iceConnectionState: string;
  signalingState: string;
}

export interface SelkiesIframeWindow extends Window {
  __getWebRTCStats?: () => Promise<SelkiesStats | null>;
}

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
