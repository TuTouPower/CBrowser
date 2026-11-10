import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "../../shared/api/client";
import type { ProfileRuntimeResponse } from "../../shared/api/types";
import { waitForRuntimeState } from "./useProfilesQuery";

function runtime(state: "stopped" | "running"): ProfileRuntimeResponse {
  return {
    profile_id: "p1",
    display_number: 1,
    desired_state: "running",
    observed_state: state,
    runtime_instance_id: null,
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    last_exit_event_id: null,
    last_coordinator_error: null,
    updated_at: "2026-11-03T00:00:00Z",
  };
}

describe("waitForRuntimeState", () => {
  it("continues after transient polling failures", async () => {
    const getRuntime = vi
      .fn()
      .mockRejectedValueOnce(new Error("transient-1"))
      .mockRejectedValueOnce(new Error("transient-2"))
      .mockResolvedValue(runtime("running"));
    const client = { profiles: { getRuntime } } as unknown as ApiClient;
    await expect(
      waitForRuntimeState(client, "p1", (r) => r.observed_state === "running", 3000),
    ).resolves.toMatchObject({ observed_state: "running" });
  });

  it("distinguishes repeated polling failure from timeout", async () => {
    const getRuntime = vi.fn().mockRejectedValue(new Error("down"));
    const client = { profiles: { getRuntime } } as unknown as ApiClient;
    await expect(
      waitForRuntimeState(client, "p1", () => false, 3000),
    ).rejects.toThrow(/polling failed/);
  });

  it("reports timeout when polling succeeds but never converges", async () => {
    const getRuntime = vi.fn().mockResolvedValue(runtime("stopped"));
    const client = { profiles: { getRuntime } } as unknown as ApiClient;
    await expect(
      waitForRuntimeState(client, "p1", () => false, 10),
    ).rejects.toThrow(/timeout/);
  });
});
