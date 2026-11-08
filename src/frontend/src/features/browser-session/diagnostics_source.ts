import {
  AUDIO_STATUS_WINDOW_MS,
  deriveAudioStatus,
  type AudioStatsSample,
  type AudioStatus,
} from "./audio_status";
import type { CandidatePairDiagnostics, SelkiesStats } from "./types";

export interface ConnectionSnapshot {
  connected: boolean;
  hasFrames: boolean;
  connectionState: string | null;
  iceConnectionState: string | null;
  signalingState: string | null;
}

export interface DiagnosticsSnapshot {
  framesDecoded?: number;
  keyFramesDecoded?: number;
  packetsLost?: number;
  packetsReceived?: number;
  roundTripTime?: number;
  totalAudioEnergy?: number;
  audioBytesReceived?: number;
  audioStatus?: AudioStatus;
  selectedPair?: CandidatePairDiagnostics | null;
}

export interface SessionDiagnosticsStoreSnapshot {
  connection: ConnectionSnapshot;
  diagnostics: DiagnosticsSnapshot;
}

export interface SessionDiagnosticsSourceOptions {
  readStats: () => Promise<SelkiesStats | null>;
  onConnectionSignal?: (snapshot: ConnectionSnapshot) => void;
  intervalMs?: number;
}

export const EMPTY_CONNECTION: ConnectionSnapshot = {
  connected: false,
  hasFrames: false,
  connectionState: null,
  iceConnectionState: null,
  signalingState: null,
};

export const EMPTY_DIAGNOSTICS: DiagnosticsSnapshot = {};

export const EMPTY_STORE: SessionDiagnosticsStoreSnapshot = {
  connection: EMPTY_CONNECTION,
  diagnostics: EMPTY_DIAGNOSTICS,
};

function sameConnection(a: ConnectionSnapshot, b: ConnectionSnapshot): boolean {
  return (
    a.connected === b.connected &&
    a.hasFrames === b.hasFrames &&
    a.connectionState === b.connectionState &&
    a.iceConnectionState === b.iceConnectionState &&
    a.signalingState === b.signalingState
  );
}

function samePair(
  a: CandidatePairDiagnostics | null | undefined,
  b: CandidatePairDiagnostics | null | undefined
): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  return (
    a.localType === b.localType &&
    a.remoteType === b.remoteType &&
    a.remoteAddress === b.remoteAddress &&
    a.remotePort === b.remotePort &&
    a.remoteUfrag === b.remoteUfrag &&
    a.roundTripTime === b.roundTripTime &&
    a.bytesReceived === b.bytesReceived
  );
}

function sameDiagnostics(
  a: DiagnosticsSnapshot,
  b: DiagnosticsSnapshot
): boolean {
  return (
    a.framesDecoded === b.framesDecoded &&
    a.keyFramesDecoded === b.keyFramesDecoded &&
    a.packetsLost === b.packetsLost &&
    a.packetsReceived === b.packetsReceived &&
    a.roundTripTime === b.roundTripTime &&
    a.totalAudioEnergy === b.totalAudioEnergy &&
    a.audioBytesReceived === b.audioBytesReceived &&
    a.audioStatus === b.audioStatus &&
    samePair(a.selectedPair, b.selectedPair)
  );
}

function finiteOrZero(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function stringOrNull(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function isDocumentHidden(): boolean {
  return typeof document !== "undefined" && document.hidden === true;
}

export class SessionDiagnosticsSource {
  private readonly readStats: () => Promise<SelkiesStats | null>;
  private readonly onConnectionSignal:
    | ((snapshot: ConnectionSnapshot) => void)
    | undefined;
  private readonly intervalMs: number;
  private readonly listeners = new Set<() => void>();
  private active = false;
  private diagnosticsEnabled = true;
  private muted = false;
  private generation = 0;
  private loopToken = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private inFlight = false;
  private audioSamples: AudioStatsSample[] = [];
  private connectionSnapshot: ConnectionSnapshot = EMPTY_CONNECTION;
  private diagnosticsSnapshot: DiagnosticsSnapshot = EMPTY_DIAGNOSTICS;
  private storeSnapshot: SessionDiagnosticsStoreSnapshot = EMPTY_STORE;

  readonly subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  readonly getSnapshot = (): SessionDiagnosticsStoreSnapshot =>
    this.storeSnapshot;

  readonly getConnectionSnapshot = (): ConnectionSnapshot =>
    this.connectionSnapshot;

  readonly getDiagnosticsSnapshot = (): DiagnosticsSnapshot =>
    this.diagnosticsSnapshot;

  constructor(options: SessionDiagnosticsSourceOptions) {
    this.readStats = options.readStats;
    this.onConnectionSignal = options.onConnectionSignal;
    this.intervalMs = options.intervalMs ?? 1000;
  }

  setGeneration(gen: number): void {
    this.generation = gen;
    this.loopToken += 1;
    this.audioSamples = [];
    this.connectionSnapshot = EMPTY_CONNECTION;
    this.diagnosticsSnapshot = EMPTY_DIAGNOSTICS;
    this.publish();
    this.cancelTimer();
    if (this.active && !this.inFlight) {
      this.schedule(0);
    }
  }

  setActive(active: boolean): void {
    if (this.active === active) return;
    this.active = active;
    this.loopToken += 1;
    this.audioSamples = [];
    this.cancelTimer();
    if (active && !this.inFlight) {
      this.schedule(0);
    }
  }

  setDiagnosticsEnabled(enabled: boolean): void {
    this.diagnosticsEnabled = enabled;
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
  }

  dispose(): void {
    this.active = false;
    this.loopToken += 1;
    this.inFlight = false;
    this.audioSamples = [];
    this.cancelTimer();
    this.listeners.clear();
  }

  private cancelTimer(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }

  private schedule(delay: number = this.intervalMs): void {
    if (!this.active || this.timer !== null || this.inFlight) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.tick();
    }, delay);
  }

  private async tick(): Promise<void> {
    if (!this.active || this.inFlight) return;
    const token = this.loopToken;
    const gen = this.generation;
    this.inFlight = true;
    let stats: SelkiesStats | null = null;
    try {
      stats = await this.readStats();
    } catch {
      stats = null;
    }
    this.inFlight = false;
    if (token !== this.loopToken || gen !== this.generation) {
      if (this.active) this.schedule(0);
      return;
    }
    if (!this.active) return;
    this.apply(stats);
    this.schedule();
  }

  private apply(stats: SelkiesStats | null): void {
    if (stats) {
      const next: ConnectionSnapshot = {
        connected: stats.connected === true,
        hasFrames: finiteOrZero(stats.video?.framesDecoded) > 0,
        connectionState: stringOrNull(stats.connectionState),
        iceConnectionState: stringOrNull(stats.iceConnectionState),
        signalingState: stringOrNull(stats.signalingState),
      };
      if (!sameConnection(this.connectionSnapshot, next)) {
        this.connectionSnapshot = next;
        this.onConnectionSignal?.(next);
      }
    }

    if (this.diagnosticsEnabled && !isDocumentHidden() && stats) {
      const now = Date.now();
      const sample: AudioStatsSample = {
        at: now,
        present: Boolean(stats.audio),
        bytesReceived: finiteOrZero(stats.audio?.bytesReceived),
        packetsReceived: finiteOrZero(stats.audio?.packetsReceived),
        totalAudioEnergy: finiteOrZero(stats.audio?.totalAudioEnergy),
      };
      const history = [...this.audioSamples, sample].filter(
        (item) => now - item.at <= AUDIO_STATUS_WINDOW_MS * 2
      );
      this.audioSamples = history;
      const prev = this.diagnosticsSnapshot;
      const next: DiagnosticsSnapshot = {
        framesDecoded: finiteOrZero(stats.video?.framesDecoded),
        keyFramesDecoded: finiteOrZero(stats.video?.keyFramesDecoded),
        packetsLost: finiteOrZero(stats.video?.packetsLost),
        packetsReceived: finiteOrZero(stats.video?.packetsReceived),
        roundTripTime: stats.pair?.roundTripTime
          ? Math.round(stats.pair.roundTripTime * 1000)
          : prev.roundTripTime,
        totalAudioEnergy: finiteOrZero(stats.audio?.totalAudioEnergy),
        audioBytesReceived: finiteOrZero(stats.audio?.bytesReceived),
        audioStatus: deriveAudioStatus(
          history,
          now,
          AUDIO_STATUS_WINDOW_MS,
          this.muted
        ),
        selectedPair: stats.pair ?? prev.selectedPair,
      };
      if (!sameDiagnostics(prev, next)) {
        this.diagnosticsSnapshot = next;
      }
    }

    this.publish();
  }

  private publish(): void {
    if (
      this.storeSnapshot.connection === this.connectionSnapshot &&
      this.storeSnapshot.diagnostics === this.diagnosticsSnapshot
    ) {
      return;
    }
    this.storeSnapshot = {
      connection: this.connectionSnapshot,
      diagnostics: this.diagnosticsSnapshot,
    };
    for (const listener of [...this.listeners]) {
      listener();
    }
  }
}
