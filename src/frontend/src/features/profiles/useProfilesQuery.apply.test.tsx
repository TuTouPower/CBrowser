import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { ApiClient } from "../../shared/api/client";
import type { ProfileRuntimeResponse } from "../../shared/api/types";
import { useApplyDisplaySettingsMutation } from "./useProfilesQuery";

function runtime(state: "stopped" | "running"): ProfileRuntimeResponse {
  return {
    profile_id: "p1",
    display_number: 1,
    desired_state: "running",
    observed_state: state,
    runtime_instance_id: "i1",
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    last_exit_event_id: null,
    last_coordinator_error: null,
    updated_at: "2026-11-03T00:00:00Z",
  };
}

describe("useApplyDisplaySettingsMutation", () => {
  it("uses distinct action keys for stop and start", async () => {
    const stopKeys: string[] = [];
    const startKeys: string[] = [];
    let phase: "running" | "stopped" = "running";
    const client = {
      profiles: {
        stop: async (_id: string, key?: string) => {
          stopKeys.push(key || "");
          phase = "stopped";
          return runtime("stopped");
        },
        setDesiredState: async (_id: string, _state: string, key?: string) => {
          startKeys.push(key || "");
          phase = "running";
          return runtime("running");
        },
        getRuntime: async () => runtime(phase),
      },
    } as unknown as ApiClient;
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(
      () => useApplyDisplaySettingsMutation(client),
      { wrapper },
    );
    await result.current.mutateAsync("p1");
    expect(stopKeys).toHaveLength(1);
    expect(startKeys).toHaveLength(1);
    expect(stopKeys[0]).not.toBe("");
    expect(startKeys[0]).not.toBe("");
    expect(stopKeys[0]).not.toBe(startKeys[0]);
  });
});
