import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import {
  useProfilesQuery,
  useProfileRuntimeQuery,
  useRuntimeSummaryQuery,
  useCreateProfileMutation,
  useProfileEventsSync,
  profileKeys,
  groupKeys,
  proxyKeys,
} from "./useProfilesQuery";
import { ApiClient } from "../../shared/api/client";
import {
  DEFAULT_PROFILE_CREATE_VALUES,
  type ProfileRuntimeResponse,
  type RuntimeSummaryResponse,
} from "../../shared/api/types";
import {
  ProfileEventsClient,
  type ProfileRuntimeEvent,
  type ReferenceChangedEvent,
} from "../../shared/api/sse";

describe("useProfilesQuery & SSE Sync", () => {
  let queryClient: QueryClient;
  let mockApiClient: ApiClient;
  let mockSseClient: ProfileEventsClient;
  let sseCallback: ((event: ProfileRuntimeEvent) => void) | null = null;
  let listCallCount = 0;
  let runtimeCallCount = 0;
  let summaryCallCount = 0;

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
    summaryCallCount = 0;
    mockApiClient.profiles.list = async () => {
      listCallCount += 1;
      return [
      {
        id: "p1",
        name: "Profile 1",
        display_number: 1,
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
        human_preset: "default",
        allow_3p_cookies: true,
        set_google_default: true,
        capture_preview: true,
        restore_session: true,
        transparent_proxy: false,
        portable_cookies: false,
        user_data_dir: "/data/p1",
        sort_order: 0,
        current_config_version: 1,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ];
    };
    mockApiClient.profiles.getRuntimeSummary = async () => {
      summaryCallCount += 1;
      return { entries: [], running_count: 0 };
    };
    mockApiClient.profiles.getRuntime = async (id: string) => {
      runtimeCallCount += 1;
      return {
        profile_id: id,
        display_number: 1,
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: null,
        config_version: 1,
        failure_count: 0,
        restart_blocked: false,
        last_exit_event_id: null,
        updated_at: "2026-01-01T00:00:00Z",
      };
    };
    mockApiClient.profiles.create = async (req) => ({
      id: "p2",
      name: req.name,
      display_number: 1,
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
      human_preset: "default",
      allow_3p_cookies: true,
      set_google_default: true,
      capture_preview: true,
      restore_session: true,
      transparent_proxy: false,
      portable_cookies: false,
      user_data_dir: "/data/p2",
      sort_order: 0,
      current_config_version: 1,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    mockApiClient.profiles.setDesiredState = async (id, state) => ({
      profile_id: id,
      display_number: 1,
      desired_state: state,
      observed_state: "starting",
      runtime_instance_id: null,
      config_version: 1,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
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
    expect(result.current.data?.[0]?.name).toBe("Profile 1");
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
      await result.current.create.mutateAsync({
        ...DEFAULT_PROFILE_CREATE_VALUES,
        name: "Created via Mutation",
      });
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
          config_version: 1,
          desired_state: "running",
          observed_state: "running",
          runtime_instance_id: "inst-999",
          failure_count: 0,
          restart_blocked: false,
          updated_at: "2026-01-01T00:00:00Z",
        });
      }
    });

    // Verify cache updated immediately
    const cachedRuntime = queryClient.getQueryData(profileKeys.runtime("p1"));
    expect(cachedRuntime).toMatchObject({
      profile_id: "p1",
      display_number: 1,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-999",
    });
  });

  // t076 AC-003 replaces the old refetch-on-SSE contract: an SSE event
  // updates the cached runtime in place and must NOT trigger a refetch
  // of the runtime query or the profile lists. The previous test
  // ("invalidates the runtime query so an SSE event refetches
  // authoritative state") asserted the removed behavior and is deleted
  // wholesale; this test pins the new one.
  it("applies an SSE event in place without refetching runtime or lists", async () => {
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
          config_version: 1,
          desired_state: "running",
          observed_state: "starting",
          runtime_instance_id: "inst-42",
          failure_count: 0,
          restart_blocked: false,
          updated_at: "2026-01-01T00:00:00Z",
        });
      }
    });

    // The event's state is visible from the cache immediately, with no
    // additional fetch: the authoritative state is the event itself.
    const cachedRuntime = queryClient.getQueryData(profileKeys.runtime("p1"));
    expect(cachedRuntime).toMatchObject({
      observed_state: "starting",
      runtime_instance_id: "inst-42",
    });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(runtimeCallCount).toBe(callsBeforeEvent);
  });

  it("does not fabricate runtime state for a profile without cached runtime data", async () => {
    renderHook(() => useProfileEventsSync(mockSseClient), { wrapper: createWrapper() });

    act(() => {
      if (sseCallback) {
        sseCallback({
          profile_id: "uncached",
          config_version: 1,
          desired_state: "running",
          observed_state: "running",
          runtime_instance_id: "inst-1",
          failure_count: 0,
          restart_blocked: false,
          updated_at: "2026-01-01T00:00:00Z",
        });
      }
    });

    // The sync never synthesizes a runtime entry from an event: a
    // profile with no cached runtime stays uncached even when its
    // event carries a config version.
    expect(queryClient.getQueryData(profileKeys.runtime("uncached"))).toBeUndefined();
  });

  // t076 review f001: list/entry pages read only the batched summary,
  // so the per-profile runtime cache is empty on first open — the
  // event must still reach the summary (fenced by the summary
  // entry's own version/instance), without synthesizing a runtime
  // entry.
  it("updates the runtime summary from an SSE event when no per-profile runtime cache exists", async () => {
    queryClient.setQueryData<RuntimeSummaryResponse>(
      profileKeys.runtimeSummary(),
      {
        entries: [
          {
            profile_id: "p1",
            desired_state: "stopped",
            observed_state: "stopped",
            config_version: 1,
            runtime_instance_id: null,
            failure_count: 0,
            restart_blocked: false,
            last_started_at: null,
            last_stopped_at: null,
            preview_captured_at: null,
            last_coordinator_error: null,
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
        running_count: 0,
      },
    );
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const summary = () =>
      queryClient.getQueryData<RuntimeSummaryResponse>(
        profileKeys.runtimeSummary(),
      );

    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 1,
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-1",
        failure_count: 0,
        restart_blocked: false,
        last_started_at: "2026-01-02T10:00:00Z",
        last_stopped_at: null,
        updated_at: "2026-01-02T10:00:00Z",
      });
    });
    expect(summary()?.entries[0]?.observed_state).toBe("running");
    expect(summary()?.entries[0]?.runtime_instance_id).toBe("inst-1");
    expect(summary()?.entries[0]?.last_started_at).toBe(
      "2026-01-02T10:00:00Z",
    );
    expect(summary()?.running_count).toBe(1);
    // No runtime entry is synthesized from the event.
    expect(queryClient.getQueryData(profileKeys.runtime("p1"))).toBeUndefined();

    // The summary entry fences stale events too: an older version
    // must not overwrite the newer summary state.
    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 0,
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: "inst-0",
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-01-02T10:01:00Z",
      });
    });
    expect(summary()?.entries[0]?.observed_state).toBe("running");
  });

  // t076 review f002: a time-only event (same states, new start time)
  // is a real change — the old change check ignored the timestamps
  // and dropped it, so rows kept showing the previous start time.
  it("copies start/stop timestamps from an SSE event into the runtime and summary caches", async () => {
    queryClient.setQueryData(profileKeys.runtime("p1"), {
      profile_id: "p1",
      display_number: 1,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-1",
      config_version: 1,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      last_coordinator_error: null,
      last_started_at: "2026-01-01T10:00:00Z",
      last_stopped_at: null,
      search_defaults: null,
      updated_at: "2026-01-01T10:00:00Z",
    });
    queryClient.setQueryData<RuntimeSummaryResponse>(
      profileKeys.runtimeSummary(),
      {
        entries: [
          {
            profile_id: "p1",
            desired_state: "running",
            observed_state: "running",
            config_version: 1,
            runtime_instance_id: "inst-1",
            failure_count: 0,
            restart_blocked: false,
            last_started_at: "2026-01-01T10:00:00Z",
            last_stopped_at: null,
            preview_captured_at: null,
            last_coordinator_error: null,
            updated_at: "2026-01-01T10:00:00Z",
          },
        ],
        running_count: 1,
      },
    );
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });

    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 1,
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-1",
        failure_count: 0,
        restart_blocked: false,
        last_started_at: "2026-01-02T10:00:00Z",
        last_stopped_at: null,
        updated_at: "2026-01-02T10:00:00Z",
      });
    });
    expect(
      queryClient.getQueryData<ProfileRuntimeResponse>(
        profileKeys.runtime("p1"),
      )?.last_started_at,
    ).toBe("2026-01-02T10:00:00Z");
    expect(
      queryClient.getQueryData<RuntimeSummaryResponse>(
        profileKeys.runtimeSummary(),
      )?.entries[0]?.last_started_at,
    ).toBe("2026-01-02T10:00:00Z");
  });

  // t076 review f002: a preview capture moves the summary entry the
  // list rows render, under the same no-regression fence.
  it("updates the summary preview time from a preview event without a per-profile runtime cache", async () => {
    let previewCallback:
      | ((event: {
          profile_id: string;
          captured_at: string;
        }) => void)
      | null = null;
    mockSseClient.onPreviewEvent = (cb) => {
      previewCallback = cb as typeof previewCallback;
      return () => {
        previewCallback = null;
      };
    };
    queryClient.setQueryData(profileKeys.collection({}), {
      items: [
        {
          id: "p1",
          name: "Profile 1",
          capture_preview: true,
        },
      ],
      total: 1,
      page: 1,
      page_size: 50,
    });
    queryClient.setQueryData<RuntimeSummaryResponse>(
      profileKeys.runtimeSummary(),
      {
        entries: [
          {
            profile_id: "p1",
            desired_state: "stopped",
            observed_state: "stopped",
            config_version: 1,
            runtime_instance_id: null,
            failure_count: 0,
            restart_blocked: false,
            last_started_at: null,
            last_stopped_at: null,
            preview_captured_at: null,
            last_coordinator_error: null,
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
        running_count: 0,
      },
    );
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const previewAt = () =>
      queryClient.getQueryData<RuntimeSummaryResponse>(
        profileKeys.runtimeSummary(),
      )?.entries[0]?.preview_captured_at;

    act(() => {
      previewCallback?.({
        profile_id: "p1",
        captured_at: "2026-01-02T10:00:00Z",
      });
    });
    expect(previewAt()).toBe("2026-01-02T10:00:00Z");

    // An older capture must not move the time backwards.
    act(() => {
      previewCallback?.({
        profile_id: "p1",
        captured_at: "2026-01-01T09:00:00Z",
      });
    });
    expect(previewAt()).toBe("2026-01-02T10:00:00Z");
  });

  // t076 review test f003: hook-level disconnect/reconnect — the sync
  // unmounts (SSE stops) and remounts (SSE restarts), then a replayed
  // event must bring the summary to the latest state without
  // triggering a full summary refetch.
  it("recovers the summary across an SSE disconnect and reconnect without refetching", async () => {
    const { result, unmount } = renderHook(
      () => ({
        summary: useRuntimeSummaryQuery(mockApiClient),
        sse: useProfileEventsSync(mockSseClient),
      }),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.summary.isSuccess).toBe(true));
    expect(summaryCallCount).toBe(1);

    // Disconnect: unmounting the hook stops the SSE client and drops
    // the subscription; the QueryClient survives.
    unmount();

    // Reconnect: a fresh mount re-subscribes, restarts the client and
    // refetches the summary (the server's snapshot after reconnect).
    // The refetch is the reconnect snapshot — the replayed event after
    // it must not trigger another one.
    mockApiClient.profiles.getRuntimeSummary = async () => {
      summaryCallCount += 1;
      return {
        entries: [
          {
            profile_id: "p1",
            desired_state: "stopped",
            observed_state: "stopped",
            config_version: 1,
            runtime_instance_id: null,
            failure_count: 0,
            restart_blocked: false,
            last_started_at: null,
            last_stopped_at: null,
            preview_captured_at: null,
            last_coordinator_error: null,
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
        running_count: 0,
      };
    };
    const second = renderHook(
      () => ({
        summary: useRuntimeSummaryQuery(mockApiClient),
        sse: useProfileEventsSync(mockSseClient),
      }),
      { wrapper: createWrapper() },
    );
    await waitFor(() =>
      expect(
        second.result.current.summary.data?.entries[0]?.profile_id,
      ).toBe("p1"),
    );
    const callsAfterReconnect = summaryCallCount;

    // The server replays the missed state change after reconnect.
    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 1,
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-9",
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-01-02T10:00:00Z",
      });
    });
    const summary = queryClient.getQueryData<RuntimeSummaryResponse>(
      profileKeys.runtimeSummary(),
    );
    expect(summary?.entries[0]?.observed_state).toBe("running");
    expect(summary?.entries[0]?.runtime_instance_id).toBe("inst-9");
    expect(summary?.running_count).toBe(1);
    expect(summaryCallCount).toBe(callsAfterReconnect);
  });

  it("merges search_defaults from runtime events into the cached runtime", async () => {
    queryClient.setQueryData(profileKeys.runtime("p1"), {
      profile_id: "p1",
      display_number: 1,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-1",
      config_version: 1,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      last_coordinator_error: null,
      search_defaults: null,
      updated_at: "2026-11-04T00:00:00Z",
    });
    renderHook(() => useProfileEventsSync(mockSseClient), { wrapper: createWrapper() });

    const status = {
      state: "failed" as const,
      error_kind: "timeout",
      runtime_instance_id: "inst-1",
      request_id: null,
      updated_at: "2026-11-04T00:01:00Z",
    };
    act(() => {
      if (sseCallback) {
        sseCallback({
          profile_id: "p1",
          config_version: 1,
          desired_state: "running",
          observed_state: "running",
          failure_count: 0,
          restart_blocked: false,
          updated_at: "2026-11-04T00:01:00Z",
          search_defaults: status,
        });
      }
    });
    const merged = queryClient.getQueryData<ProfileRuntimeResponse>(
      profileKeys.runtime("p1"),
    );
    expect(merged?.search_defaults).toEqual(status);

    // An event without the field leaves the cached status untouched.
    act(() => {
      if (sseCallback) {
        sseCallback({
          profile_id: "p1",
          config_version: 1,
          desired_state: "running",
          observed_state: "running",
          failure_count: 0,
          restart_blocked: false,
          updated_at: "2026-11-04T00:02:00Z",
        });
      }
    });
    expect(
      queryClient.getQueryData<ProfileRuntimeResponse>(profileKeys.runtime("p1"))
        ?.search_defaults,
    ).toEqual(status);
  });

  // t076 AC-003: version/instance fencing — a late event from an older
  // bound config version, or from a superseded instance at the same
  // version, must not overwrite newer cached state; a byte-identical
  // replay must not touch the cache at all.
  it("ignores stale-version, stale-instance and duplicate SSE events", async () => {
    queryClient.setQueryData(profileKeys.runtime("p1"), {
      profile_id: "p1",
      display_number: 1,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-new",
      config_version: 3,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      last_coordinator_error: null,
      search_defaults: null,
      updated_at: "2026-11-04T00:00:00Z",
    });
    renderHook(() => useProfileEventsSync(mockSseClient), { wrapper: createWrapper() });
    const cached = () =>
      queryClient.getQueryData<ProfileRuntimeResponse>(profileKeys.runtime("p1"));

    act(() => {
      sseCallback?.({
        profile_id: "p1",
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: "inst-old",
        config_version: 2,
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-11-04T00:01:00Z",
      });
    });
    expect(cached()?.observed_state).toBe("running");
    expect(cached()?.runtime_instance_id).toBe("inst-new");

    act(() => {
      sseCallback?.({
        profile_id: "p1",
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: "inst-other",
        config_version: 3,
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-11-04T00:01:00Z",
      });
    });
    expect(cached()?.observed_state).toBe("running");
    expect(cached()?.runtime_instance_id).toBe("inst-new");

    const before = cached();
    act(() => {
      sseCallback?.({
        profile_id: "p1",
        desired_state: "running",
        observed_state: "running",
        runtime_instance_id: "inst-new",
        config_version: 3,
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-11-04T00:00:00Z",
      });
    });
    expect(cached()).toBe(before);
  });

  // t076 review f009: the two caches usually disagree on version —
  // the summary is refetched on every list focus/remount while the
  // per-profile runtime cache is only refetched on a detail visit.
  // Each cache must fence by its OWN version/instance: a late v1
  // event must not roll the v2 summary back, even when the v1
  // runtime cache lets it through.
  it("fences each cache by its own version when the caches disagree (runtime v1, summary v2)", async () => {
    queryClient.setQueryData(profileKeys.runtime("p1"), {
      profile_id: "p1",
      display_number: 1,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-1",
      config_version: 1,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      last_coordinator_error: null,
      search_defaults: null,
      updated_at: "2026-11-04T00:00:00Z",
    });
    queryClient.setQueryData<RuntimeSummaryResponse>(
      profileKeys.runtimeSummary(),
      {
        entries: [
          {
            profile_id: "p1",
            desired_state: "running",
            observed_state: "running",
            config_version: 2,
            runtime_instance_id: "inst-2",
            failure_count: 0,
            restart_blocked: false,
            last_started_at: "2026-11-04T00:00:00Z",
            last_stopped_at: null,
            preview_captured_at: null,
            last_coordinator_error: null,
            updated_at: "2026-11-04T00:00:00Z",
          },
        ],
        running_count: 1,
      },
    );
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const summary = () =>
      queryClient.getQueryData<RuntimeSummaryResponse>(
        profileKeys.runtimeSummary(),
      );

    // The reviewer's repro: a replayed/late v1 event for instance
    // inst-1 arrives after the summary already moved to v2/inst-2.
    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 1,
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: "inst-1",
        failure_count: 0,
        restart_blocked: false,
        updated_at: "2026-11-04T00:01:00Z",
      });
    });
    // The v1 runtime cache's own fence passes, so it moves — but the
    // v2 summary must not be rolled back to the old event.
    expect(
      queryClient.getQueryData<ProfileRuntimeResponse>(
        profileKeys.runtime("p1"),
      )?.observed_state,
    ).toBe("stopped");
    expect(summary()?.entries[0]?.observed_state).toBe("running");
    expect(summary()?.entries[0]?.config_version).toBe(2);
    expect(summary()?.entries[0]?.runtime_instance_id).toBe("inst-2");
  });

  // t076 review f009, opposite direction: a stale v1 event passes
  // the v1 summary's fence but must not touch the v2 runtime cache.
  it("fences each cache by its own version when the caches disagree (runtime v2, summary v1)", async () => {
    queryClient.setQueryData(profileKeys.runtime("p1"), {
      profile_id: "p1",
      display_number: 1,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-2",
      config_version: 2,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      last_coordinator_error: null,
      search_defaults: null,
      updated_at: "2026-11-04T00:00:00Z",
    });
    queryClient.setQueryData<RuntimeSummaryResponse>(
      profileKeys.runtimeSummary(),
      {
        entries: [
          {
            profile_id: "p1",
            desired_state: "running",
            observed_state: "running",
            config_version: 1,
            runtime_instance_id: "inst-1",
            failure_count: 0,
            restart_blocked: false,
            last_started_at: "2026-11-04T00:00:00Z",
            last_stopped_at: null,
            preview_captured_at: null,
            last_coordinator_error: null,
            updated_at: "2026-11-04T00:00:00Z",
          },
        ],
        running_count: 1,
      },
    );
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const summary = () =>
      queryClient.getQueryData<RuntimeSummaryResponse>(
        profileKeys.runtimeSummary(),
      );

    act(() => {
      sseCallback?.({
        profile_id: "p1",
        config_version: 1,
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: "inst-1",
        failure_count: 0,
        restart_blocked: false,
        last_stopped_at: "2026-11-04T00:01:00Z",
        updated_at: "2026-11-04T00:01:00Z",
      });
    });
    expect(
      queryClient.getQueryData<ProfileRuntimeResponse>(
        profileKeys.runtime("p1"),
      )?.observed_state,
    ).toBe("running");
    expect(
      queryClient.getQueryData<ProfileRuntimeResponse>(
        profileKeys.runtime("p1"),
      )?.config_version,
    ).toBe(2);
    expect(summary()?.entries[0]?.observed_state).toBe("stopped");
    expect(summary()?.entries[0]?.config_version).toBe(1);
    expect(summary()?.entries[0]?.last_stopped_at).toBe(
      "2026-11-04T00:01:00Z",
    );
    expect(summary()?.running_count).toBe(0);
  });

  // t076 review test f010: an event without config_version predates
  // the fence and is treated as current for both caches. The wire
  // parser casts raw JSON (`parseProfileRuntimeEvent` returns
  // `raw as ProfileRuntimeEvent`), so a version-less event is a real
  // runtime input even though the generated type marks the field
  // required — the cast below simulates exactly that wire shape.
  // The test pins both `??` branches: the fence must let the event
  // through, and the merge must keep each cache's own version
  // instead of writing undefined into it.
  it("treats a version-less SSE event as current for both caches", async () => {
    queryClient.setQueryData(profileKeys.runtime("p1"), {
      profile_id: "p1",
      display_number: 1,
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst-2",
      config_version: 2,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      last_coordinator_error: null,
      search_defaults: null,
      updated_at: "2026-11-04T00:00:00Z",
    });
    queryClient.setQueryData<RuntimeSummaryResponse>(
      profileKeys.runtimeSummary(),
      {
        entries: [
          {
            profile_id: "p1",
            desired_state: "running",
            observed_state: "running",
            config_version: 2,
            runtime_instance_id: "inst-2",
            failure_count: 0,
            restart_blocked: false,
            last_started_at: "2026-11-04T00:00:00Z",
            last_stopped_at: null,
            preview_captured_at: null,
            last_coordinator_error: null,
            updated_at: "2026-11-04T00:00:00Z",
          },
        ],
        running_count: 1,
      },
    );
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const summary = () =>
      queryClient.getQueryData<RuntimeSummaryResponse>(
        profileKeys.runtimeSummary(),
      );

    act(() => {
      sseCallback?.({
        profile_id: "p1",
        desired_state: "stopped",
        observed_state: "stopped",
        runtime_instance_id: "inst-2",
        failure_count: 0,
        restart_blocked: false,
        last_stopped_at: "2026-11-04T00:01:00Z",
        updated_at: "2026-11-04T00:01:00Z",
      } as ProfileRuntimeEvent);
    });
    expect(
      queryClient.getQueryData<ProfileRuntimeResponse>(
        profileKeys.runtime("p1"),
      ),
    ).toMatchObject({
      observed_state: "stopped",
      desired_state: "stopped",
      runtime_instance_id: "inst-2",
      config_version: 2,
      last_stopped_at: "2026-11-04T00:01:00Z",
    });
    expect(summary()?.entries[0]).toMatchObject({
      observed_state: "stopped",
      desired_state: "stopped",
      runtime_instance_id: "inst-2",
      config_version: 2,
      last_stopped_at: "2026-11-04T00:01:00Z",
    });
    expect(summary()?.running_count).toBe(0);
  });

  it("invalidates group and profile lists on a groups_changed event (t056 A31)", async () => {
    let referenceCallback: ((event: ReferenceChangedEvent) => void) | null =
      null;
    mockSseClient.onReferenceEvent = (cb) => {
      referenceCallback = cb;
      return () => {
        referenceCallback = null;
      };
    };
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    act(() => {
      referenceCallback?.({ event: "groups_changed", entity_id: "g1" });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: groupKeys.lists(),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: profileKeys.lists(),
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: proxyKeys.lists(),
    });
  });

  it("invalidates proxy and profile lists on a proxies_changed event (t056 A31)", async () => {
    let referenceCallback: ((event: ReferenceChangedEvent) => void) | null =
      null;
    mockSseClient.onReferenceEvent = (cb) => {
      referenceCallback = cb;
      return () => {
        referenceCallback = null;
      };
    };
    renderHook(() => useProfileEventsSync(mockSseClient), {
      wrapper: createWrapper(),
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    act(() => {
      referenceCallback?.({ event: "proxies_changed", entity_id: null });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: proxyKeys.lists(),
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: profileKeys.lists(),
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: groupKeys.lists(),
    });
  });
});
