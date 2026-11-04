import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import {
  ApiError,
  shouldRetryRequest,
  type ApiClient,
} from "../../shared/api/client";
import type { ProfileRuntimeResponse } from "../../shared/api/types";
import { useApplyDisplaySettingsMutation } from "./useProfilesQuery";

/**
 * AC-004 (t025): one apply action is a staged logical action. When React
 * Query retries the mutationFn with the same action key, the retry must
 * resume from the stage the server actually reached instead of replaying
 * the stop step and waiting for a stopped state that will never come.
 *
 * The fake backend models the server's idempotency contract: a repeated
 * operation key replays as a no-op without changing runtime state.
 */
function makeBackend() {
  const state = {
    desired: "running",
    observed: "running",
    instance: "i1" as string | null,
  };
  const appliedKeys = new Set<string>();
  const calls = {
    stop: [] as (string | undefined)[],
    start: [] as (string | undefined)[],
    getRuntime: 0,
  };
  const script = {
    stopPlan: [] as ("throw" | "apply-then-throw")[],
    startPlan: [] as ("throw" | "apply-then-throw")[],
    getRuntimeFailures: 0,
    onStopApplied: null as (() => void) | null,
    recoverOldInstanceOnStartThrow: false,
  };
  const snapshot = (): ProfileRuntimeResponse =>
    ({
      profile_id: "p1",
      desired_state: state.desired,
      observed_state: state.observed,
      runtime_instance_id: state.instance,
      config_version: 1,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      last_coordinator_error: null,
      updated_at: "2026-11-04T00:00:00Z",
    }) as ProfileRuntimeResponse;
  const timeoutError = () =>
    new ApiError("Request timed out", 0, undefined, "timeout", true);

  const client = {
    profiles: {
      getRuntime: async () => {
        calls.getRuntime += 1;
        if (script.getRuntimeFailures > 0) {
          script.getRuntimeFailures -= 1;
          throw new Error("transient runtime query failure");
        }
        return snapshot();
      },
      stop: async (_id: string, key?: string) => {
        calls.stop.push(key);
        const plan = script.stopPlan.shift();
        if (plan === "throw") throw timeoutError();
        if (key && appliedKeys.has(key)) {
          // Idempotent replay: returns the stored response, changes nothing.
          return snapshot();
        }
        if (key) appliedKeys.add(key);
        state.observed = "stopped";
        script.onStopApplied?.();
        if (plan === "apply-then-throw") throw timeoutError();
        return snapshot();
      },
      setDesiredState: async (
        _id: string,
        _desired: string,
        key?: string,
      ) => {
        calls.start.push(key);
        const plan = script.startPlan.shift();
        if (plan === "throw") {
          if (script.recoverOldInstanceOnStartThrow) {
            // An external actor restarted the pre-stop instance before
            // the retry: the old epoch (and its stop effect) is gone.
            state.observed = "running";
            for (const k of [...appliedKeys]) {
              if (k.endsWith(":stop")) appliedKeys.delete(k);
            }
          }
          throw timeoutError();
        }
        if (key && appliedKeys.has(key)) {
          return snapshot();
        }
        if (key) appliedKeys.add(key);
        state.desired = "running";
        state.observed = "running";
        state.instance = "i2";
        if (plan === "apply-then-throw") throw timeoutError();
        return snapshot();
      },
    },
  } as unknown as ApiClient;
  return { client, state, calls, script };
}

function renderApply(client: ApiClient) {
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: { retry: shouldRetryRequest, retryDelay: 0 },
    },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => useApplyDisplaySettingsMutation(client), {
    wrapper,
  });
}

describe("useApplyDisplaySettingsMutation stage resume", () => {
  it(
    "resumes after start took effect but its response was lost: no second stop, no wait for stopped",
    { timeout: 20_000 },
    async () => {
      const backend = makeBackend();
      backend.script.startPlan = ["apply-then-throw"];
      const { result } = renderApply(backend.client);
      const final = await result.current.mutateAsync("p1");
      expect(final.observed_state).toBe("running");
      expect(final.runtime_instance_id).toBe("i2");
      expect(backend.calls.stop).toHaveLength(1);
      expect(backend.calls.start).toHaveLength(1);
    },
  );

  it("resumes after stop took effect but start was never applied: skips the stop step", async () => {
    const backend = makeBackend();
    backend.script.startPlan = ["throw"];
    const { result } = renderApply(backend.client);
    const final = await result.current.mutateAsync("p1");
    expect(final.observed_state).toBe("running");
    expect(final.runtime_instance_id).toBe("i2");
    expect(backend.calls.stop).toHaveLength(1);
    expect(backend.calls.start).toHaveLength(2);
    expect(backend.calls.start[0]).toBe(backend.calls.start[1]);
  });

  it("does not skip stop/start when the pre-stop instance was externally restored", async () => {
    const backend = makeBackend();
    backend.script.startPlan = ["throw"];
    backend.script.recoverOldInstanceOnStartThrow = true;
    const { result } = renderApply(backend.client);
    const final = await result.current.mutateAsync("p1");
    expect(final.observed_state).toBe("running");
    // desired/observed alone look like "start already effective", but
    // the instance is still the pre-stop one: the retry must run the
    // full stop/start and converge on a genuinely new instance.
    expect(final.runtime_instance_id).toBe("i2");
    expect(backend.calls.stop).toHaveLength(2);
    expect(backend.calls.start).toHaveLength(2);
  });

  it("re-runs the stop step when stop never took effect", async () => {
    const backend = makeBackend();
    backend.script.stopPlan = ["throw"];
    const { result } = renderApply(backend.client);
    const final = await result.current.mutateAsync("p1");
    expect(final.observed_state).toBe("running");
    expect(backend.calls.stop).toHaveLength(2);
    expect(backend.calls.start).toHaveLength(1);
  });

  it("tolerates transient runtime query failures while waiting for stopped", async () => {
    const backend = makeBackend();
    backend.script.onStopApplied = () => {
      backend.script.getRuntimeFailures = 2;
    };
    const { result } = renderApply(backend.client);
    const final = await result.current.mutateAsync("p1");
    expect(final.observed_state).toBe("running");
    expect(backend.calls.stop).toHaveLength(1);
    expect(backend.calls.start).toHaveLength(1);
  });

  it("fails bounded without sending stop when the runtime query keeps failing", async () => {
    const backend = makeBackend();
    backend.script.getRuntimeFailures = 100;
    const { result } = renderApply(backend.client);
    await expect(result.current.mutateAsync("p1")).rejects.toThrow();
    expect(backend.calls.stop).toHaveLength(0);
    expect(backend.calls.start).toHaveLength(0);
  });
});
