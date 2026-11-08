import type { ProfileRuntimeResponse } from "../../shared/api/types";
import type { SessionStage } from "./types";

export type RuntimeObservedState = ProfileRuntimeResponse["observed_state"];

const TERMINAL_STAGES: SessionStage[] = [
  "runtime_not_ready",
  "signaling_failed",
  "web_locks_unavailable",
  "ice_failed",
  "media_no_frames",
  "error",
  "stopping",
];

export function deriveSessionStage(
  stage: SessionStage,
  observed: RuntimeObservedState | null | undefined
): SessionStage {
  if (observed === "stopping") return "stopping";
  if (observed === "error") return "error";
  if (observed && observed !== "running" && observed !== "starting") {
    return "runtime_not_ready";
  }
  return stage;
}

export function isTerminalStage(stage: SessionStage): boolean {
  return TERMINAL_STAGES.includes(stage);
}
