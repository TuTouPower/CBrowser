import { describe, expect, it } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import {
  ApiError,
  shouldRetryRequest,
  type ApiClient,
} from "../../shared/api/client";
import {
  DEFAULT_PROFILE_CREATE_VALUES,
  type ProfileRuntimeResponse,
} from "../../shared/api/types";
import {
  useCreateProfileMutation,
  useRetrySearchDefaultsMutation,
  useSetDesiredStateMutation,
} from "./useProfilesQuery";

function runtime(id: string): ProfileRuntimeResponse {
  return {
    profile_id: id,
    display_number: 1,
    desired_state: "running",
    observed_state: "starting",
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    updated_at: "2026-11-04T00:00:00Z",
  } as ProfileRuntimeResponse;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (err: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function makeWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("per-action idempotency keys (A19)", () => {
  it("concurrent calls of one mutation instance use different keys", async () => {
    const seen: { id: string; key: string }[] = [];
    const gate = deferred<ProfileRuntimeResponse>();
    const client = {
      profiles: {
        setDesiredState: (id: string, _state: string, key?: string) => {
          seen.push({ id, key: key || "" });
          return gate.promise;
        },
      },
    } as unknown as ApiClient;
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    const { result } = renderHook(() => useSetDesiredStateMutation(client), {
      wrapper: makeWrapper(queryClient),
    });

    act(() => {
      result.current.mutate({ id: "p1", state: "running" });
      result.current.mutate({ id: "p2", state: "running" });
    });
    await waitFor(() => expect(seen).toHaveLength(2));
    expect(seen[0]?.key).not.toBe("");
    expect(seen[1]?.key).not.toBe("");
    expect(seen[0]?.key).not.toBe(seen[1]?.key);

    gate.resolve(runtime("p1"));
  });

  it("a retrying action keeps its key while another action is in flight, and settling one does not disturb the other", async () => {
    const attempts: { id: string; key: string }[] = [];
    let p1Attempts = 0;
    const p2Gate = deferred<ProfileRuntimeResponse>();
    const client = {
      profiles: {
        setDesiredState: async (id: string, _state: string, key?: string) => {
          attempts.push({ id, key: key || "" });
          if (id === "p1") {
            p1Attempts += 1;
            if (p1Attempts === 1) {
              throw new ApiError("busy", 503, undefined, "database_busy", true);
            }
            return runtime(id);
          }
          return p2Gate.promise;
        },
      },
    } as unknown as ApiClient;
    const queryClient = new QueryClient({
      defaultOptions: {
        mutations: { retry: shouldRetryRequest, retryDelay: 0 },
      },
    });
    const { result } = renderHook(() => useSetDesiredStateMutation(client), {
      wrapper: makeWrapper(queryClient),
    });

    act(() => {
      result.current.mutate({ id: "p2", state: "running" });
    });
    await result.current.mutateAsync({ id: "p1", state: "running" });

    const p1Keys = attempts.filter((a) => a.id === "p1").map((a) => a.key);
    const p2Keys = attempts.filter((a) => a.id === "p2").map((a) => a.key);
    expect(p1Keys).toHaveLength(2);
    expect(p1Keys[0]).not.toBe("");
    expect(p1Keys[1]).toBe(p1Keys[0]);
    expect(p2Keys).toHaveLength(1);
    expect(p2Keys[0]).not.toBe(p1Keys[0]);

    p2Gate.resolve(runtime("p2"));
  });

  it("search-defaults retries carry a per-action key the backend deduplicates on (A19)", async () => {
    // The backend turns the Idempotency-Key into the end-to-end
    // request_id: a retry with the same key is deduplicated, while two
    // distinct user actions must not share one.
    const seen: { id: string; key: string }[] = [];
    let attempts = 0;
    const client = {
      profiles: {
        retrySearchDefaults: async (id: string, key?: string) => {
          seen.push({ id, key: key || "" });
          attempts += 1;
          if (attempts === 1) {
            throw new ApiError("busy", 503, undefined, "database_busy", true);
          }
          return runtime(id);
        },
      },
    } as unknown as ApiClient;
    const queryClient = new QueryClient({
      defaultOptions: {
        mutations: { retry: shouldRetryRequest, retryDelay: 0 },
      },
    });
    const { result } = renderHook(() => useRetrySearchDefaultsMutation(client), {
      wrapper: makeWrapper(queryClient),
    });

    // One logical action, retried once: same key on both attempts.
    await result.current.mutateAsync("p1");
    expect(seen).toHaveLength(2);
    expect(seen[0]?.key).not.toBe("");
    expect(seen[1]?.key).toBe(seen[0]?.key);

    // A second logical action mints a fresh key.
    await result.current.mutateAsync("p1");
    expect(seen).toHaveLength(3);
    expect(seen[2]?.key).not.toBe("");
    expect(seen[2]?.key).not.toBe(seen[0]?.key);
  });

  it("two sequential calls are distinct logical actions with distinct keys", async () => {
    const keys: string[] = [];
    const client = {
      profiles: {
        create: async (data: { name: string }, key?: string) => {
          keys.push(key || "");
          return { id: `id-${data.name}` };
        },
      },
    } as unknown as ApiClient;
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    const { result } = renderHook(() => useCreateProfileMutation(client), {
      wrapper: makeWrapper(queryClient),
    });

    await result.current.mutateAsync({
      ...DEFAULT_PROFILE_CREATE_VALUES,
      name: "one",
    });
    await result.current.mutateAsync({
      ...DEFAULT_PROFILE_CREATE_VALUES,
      name: "two",
    });
    expect(keys).toHaveLength(2);
    expect(keys[0]).not.toBe("");
    expect(keys[1]).not.toBe("");
    expect(keys[0]).not.toBe(keys[1]);
  });
});
