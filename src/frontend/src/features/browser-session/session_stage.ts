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
  // P1-11: 初检 checking_runtime 遇 running/starting 直接推进到
  // connecting_signaling，避免首屏卡死；runtime_not_ready 的恢复由
  // useBrowserSession 的 runtime 恢复 effect 推进（需触发 reloadKey），
  // 此处保持原语义以保留 stopped 时的 launch 入口。
  if (
    (observed === "running" || observed === "starting") &&
    stage === "checking_runtime"
  ) {
    return "connecting_signaling";
  }
  if (observed === "stopped") {
    return "runtime_not_ready";
  }
  return stage;
}

export function isTerminalStage(stage: SessionStage): boolean {
  return TERMINAL_STAGES.includes(stage);
}
