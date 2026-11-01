import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import {
  useProfilesQuery,
  useProfileRuntimeQuery,
  useCreateProfileMutation,
  useSetDesiredStateMutation,
  useProfileEventsSync,
  profileKeys,
} from "./useProfilesQuery";
import { ApiClient } from "../../shared/api/client";
import { ProfileEventsClient, type ProfileRuntimeEvent } from "../../shared/api/sse";

describe("useProfilesQuery & SSE Sync", () => {
  let queryClient: QueryClient;
  let mockApiClient: ApiClient;
  let mockSseClient: ProfileEventsClient;
  let sseCallback: ((event: ProfileRuntimeEvent) => void) | null = null;
  let listCallCount = 0;
  let runtimeCallCount = 0;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    mockApiClient = new ApiClient();
    listCallCount = 0;
    runtimeCallCount = 0;
    mockApiClient.profiles.list = async () => {
      listCallCount += 1;
      return [
      {
        id: "p1",
        name: "Profile 1",
        fingerprint_seed: 100,
        screen_width: 1920,
        screen_height: 1080,
        gpu_family: "auto",
        humanize: false,
        geoip: false,
        clipboard_sync: false,
        auto_launch: false,
        launch_args: [],
        extension_paths: [],
        tags: ["work"],
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ];
    };
    mockApiClient.profiles.getRuntime = async (id: string) => {
      runtimeCallCount += 1;
      return {
        profile_id: id,
        desired_state: "stopped",
        observed_state: "stopped",
        config_version: 1,
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-01-01T00:00:00Z",
      };
    };
    mockApiClient.profiles.create = async (req) => ({
      id: "p2",
      name: req.name,
      fingerprint_seed: 200,
      screen_width: 1920,
      screen_height: 1080,
      gpu_family: "auto",
      humanize: false,
      geoip: false,
      clipboard_sync: false,
      auto_launch: false,
      launch_args: [],
      extension_paths: [],
      tags: [],
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    mockApiClient.profiles.setDesiredState = async (id, state) => ({
      profile_id: id,
      desired_state: state,
      observed_state: "starting",
      config_version: 1,
      failure_count: 0,
      restart_blocked: false,
      updated_at: "2026-01-01T00:00:00Z",
    });

    mockSseClient = new ProfileEventsClient();
    mockSseClient.onEvent = (cb) => {
      sseCallback = cb;
      return () => {
        sseCallback = null;
      };
    };
    mockSseClient.start = () => {};
    mockSseClient.close = () => {};
  });

  const createWrapper = () => {
    return ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children);
  };

  it("fetches profile list using TanStack Query", async () => {
    const { result } = renderHook(() => useProfilesQuery(mockApiClient), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
    expect(result.current.data?.[0].name).toBe("Profile 1");
  });

  it("creates a profile and invalidates the profiles cache", async () => {
    const { result } = renderHook(
      () => ({
        list: useProfilesQuery(mockApiClient),
        create: useCreateProfileMutation(mockApiClient),
      }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));

    await act(async () => {
      await result.current.create.mutateAsync({ name: "Created via Mutation" });
    });

    await waitFor(() => expect(result.current.create.isSuccess).toBe(true));
    await waitFor(() => expect(listCallCount).toBeGreaterThanOrEqual(2));
    expect(
      queryClient.getQueryData<Array<{ name: string }>>(profileKeys.lists()),
    ).toBeDefined();
  });

  it("updates runtime query cache dynamically when SSE event arrives", async () => {
    const { result } = renderHook(
      () => ({
        runtime: useProfileRuntimeQuery("p1", mockApiClient),
        sse: useProfileEventsSync(mockSseClient),
      }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.runtime.isSuccess).toBe(true));
    expect(result.current.runtime.data?.observed_state).toBe("stopped");

    // Simulate SSE push
    act(() => {
      if (sseCallback) {
        sseCallback({
          profile_id: "p1",
          desired_state: "running",
          observed_state: "running",
          runtime_instance_id: "inst-999",
        });
      }
    });

    // Verify cache updated immediately
    const cachedRuntime = queryClient.getQueryData(profileKeys.runtime("p1"));
    expect(cachedRuntime).toMatchObject({
      profile_id: "p1",
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-999",
    });
  });

  it("invalidates the runtime query so an SSE event refetches authoritative state", async () => {
    const { result } = renderHook(
      () => ({
        runtime: useProfileRuntimeQuery("p1", mockApiClient),
        sse: useProfileEventsSync(mockSseClient),
      }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.runtime.isSuccess).toBe(true));
    const callsBeforeEvent = runtimeCallCount;

    act(() => {
      if (sseCallback) {
        sseCallback({
          profile_id: "p1",
          desired_state: "running",
          observed_state: "starting",
          runtime_instance_id: "inst-42",
        });
      }
    });

    await waitFor(() => expect(runtimeCallCount).toBeGreaterThan(callsBeforeEvent));
    expect(result.current.runtime.data?.observed_state).toBe("stopped");
  });

  it("does not fabricate runtime state for a profile without cached runtime data", async () => {
    renderHook(() => useProfileEventsSync(mockSseClient), { wrapper: createWrapper() });

    act(() => {
      if (sseCallback) {
        sseCallback({
          profile_id: "uncached",
          desired_state: "running",
          observed_state: "running",
          runtime_instance_id: "inst-1",
        });
      }
    });

    // Events carry no config_version; inventing one would make the page report
    // pending display settings for a profile it never loaded.
    expect(queryClient.getQueryData(profileKeys.runtime("uncached"))).toBeUndefined();
  });
});
