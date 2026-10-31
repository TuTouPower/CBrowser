/**
 * Audio pipeline diagnostics derived from RTCPeerConnection getStats.
 *
 * The status is intentionally independent from the video stage: a healthy video
 * path with a broken audio path must report connected video + a distinct audio
 * fault. Silence is not a fault: Opus/DTX still emits RTP packets whose byte
 * counters grow, so only a frozen inbound audio track is reported as no_data.
 */

export type AudioStatus = "unknown" | "no_track" | "no_data" | "normal" | "muted";

export interface AudioStatsSample {
  at: number;
  present: boolean;
  bytesReceived: number;
  packetsReceived: number;
  totalAudioEnergy?: number;
}

export const AUDIO_STATUS_WINDOW_MS = 3000;

const WARMUP_RATIO = 0.8;

export function deriveAudioStatus(
  samples: readonly AudioStatsSample[],
  now: number,
  windowMs: number = AUDIO_STATUS_WINDOW_MS,
  muted = false
): AudioStatus {
  if (muted) return "muted";
  const recent = samples.filter(
    (sample) => now - sample.at <= windowMs * 2 && sample.at <= now
  );
  if (recent.length === 0) return "unknown";

  // Warm-up is measured from the start of the retained history, not from the
  // first in-window sample: with ~1s polling the oldest in-window sample is
  // routinely younger than the window and healthy audio would flap to unknown.
  if (now - recent[0]!.at < windowMs * WARMUP_RATIO) return "unknown";

  const windowStart = now - windowMs;
  const inWindow = recent.filter((sample) => sample.at >= windowStart);
  const present = inWindow.filter((sample) => sample.present);
  if (present.length === 0) return "no_track";

  // Compare against the last present sample at or before the window start so
  // the growth check always spans the full window.
  const baseline = recent.filter((sample) => sample.at < windowStart && sample.present);
  const first = baseline[baseline.length - 1] ?? present[0]!;
  const last = recent[recent.length - 1]!;
  if (!last.present) return "no_data";
  if (
    last.bytesReceived > first.bytesReceived ||
    last.packetsReceived > first.packetsReceived
  ) {
    return "normal";
  }
  return "no_data";
}
