import { describe, it, expect } from "vitest";
import {
  AUDIO_STATUS_WINDOW_MS,
  deriveAudioStatus,
  type AudioStatsSample,
} from "./audio_status";

function samples(
  values: Array<Partial<AudioStatsSample> & { at: number }>
): AudioStatsSample[] {
  return values.map((value) => ({
    at: value.at,
    present: value.present ?? true,
    bytesReceived: value.bytesReceived ?? 0,
    packetsReceived: value.packetsReceived ?? 0,
    ...(value.totalAudioEnergy !== undefined
      ? { totalAudioEnergy: value.totalAudioEnergy }
      : {}),
  }));
}

describe("deriveAudioStatus", () => {
  const now = 10_000;

  it("reports unknown while the observation window is still warming up", () => {
    const history = samples([
      { at: now - 500, bytesReceived: 100, packetsReceived: 5 },
    ]);
    expect(deriveAudioStatus(history, now)).toBe("unknown");
  });

  it("reports no_track when no inbound audio track exists for the window", () => {
    const history = samples([
      { at: now - 3000, present: false },
      { at: now - 2000, present: false },
      { at: now, present: false },
    ]);
    expect(deriveAudioStatus(history, now)).toBe("no_track");
  });

  it("reports no_data when the audio track makes no progress", () => {
    const history = samples([
      { at: now - 3000, bytesReceived: 4096, packetsReceived: 20 },
      { at: now - 2000, bytesReceived: 4096, packetsReceived: 20 },
      { at: now, bytesReceived: 4096, packetsReceived: 20 },
    ]);
    expect(deriveAudioStatus(history, now)).toBe("no_data");
  });

  it("reports normal when audio bytes keep growing", () => {
    const history = samples([
      { at: now - 3000, bytesReceived: 4096, packetsReceived: 20 },
      { at: now - 2000, bytesReceived: 8192, packetsReceived: 40 },
      { at: now, bytesReceived: 12288, packetsReceived: 60 },
    ]);
    expect(deriveAudioStatus(history, now)).toBe("normal");
  });

  it("does not treat silent Opus/DTX packets as an audio fault", () => {
    const history = samples([
      { at: now - 3000, bytesReceived: 4096, packetsReceived: 20, totalAudioEnergy: 0 },
      { at: now - 2000, bytesReceived: 4196, packetsReceived: 40, totalAudioEnergy: 0 },
      { at: now, bytesReceived: 4296, packetsReceived: 60, totalAudioEnergy: 0 },
    ]);
    expect(deriveAudioStatus(history, now)).toBe("normal");
  });

  it("reports the local mute action as muted, not as an audio fault", () => {
    const history = samples([
      { at: now - 3000, bytesReceived: 4096, packetsReceived: 20 },
      { at: now, bytesReceived: 4096, packetsReceived: 20 },
    ]);
    expect(deriveAudioStatus(history, now, AUDIO_STATUS_WINDOW_MS, true)).toBe(
      "muted"
    );
  });

  it("uses the configured window and tolerates sub-window spans", () => {
    const history = samples([
      { at: now - 1000, bytesReceived: 4096, packetsReceived: 20 },
      { at: now, bytesReceived: 4096, packetsReceived: 20 },
    ]);
    expect(deriveAudioStatus(history, now, AUDIO_STATUS_WINDOW_MS / 2)).toBe(
      "unknown"
    );
  });

  it("keeps reporting normal for healthy audio sampled about once per second", () => {
    // Mirrors the ~1.05s getStats polling cadence: once warmed up, a growing
    // audio track must never flap back to unknown.
    const history: AudioStatsSample[] = [];
    const statuses: string[] = [];
    for (let i = 0; i < 14; i += 1) {
      const at = 1_000_000 + i * 1050;
      history.push({
        at,
        present: true,
        bytesReceived: 4096 + i * 2000,
        packetsReceived: 20 + i * 50,
        totalAudioEnergy: 0,
      });
      const recent = history.filter((sample) => at - sample.at <= AUDIO_STATUS_WINDOW_MS * 2);
      statuses.push(deriveAudioStatus(recent, at));
    }
    expect(statuses.slice(0, 2)).toEqual(["unknown", "unknown"]);
    expect(statuses.slice(3)).toEqual(Array(11).fill("normal"));
  });
});
