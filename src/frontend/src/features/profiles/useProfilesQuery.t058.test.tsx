import { describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ApiClient } from "../../shared/api/client";
import type { ProfileResponse } from "../../shared/api/types";
import {
  profileKeys,
  useProfileQuery,
  useUpdateProfileMutation,
} from "./useProfilesQuery";

function profile(overrides: Partial<ProfileResponse> = {}): ProfileResponse {
  return {
    id: "p1",
    name: "Original",
    display_number: 1,
    fingerprint_seed: 101,
    group_id: null,
    proxy_id: null,
    timezone: null,
    locale: null,
    screen_width: 1920,
    screen_height: 1080,
    gpu_family: "auto",
    humanize: false,
    human_preset: "default",
    geoip: true,
    clipboard_sync: true,
    auto_launch: false,
    color_scheme: null,
    fingerprint_platform: "windows",
    font_set_id: null,
    launch_args: [],
    extension_paths: [],
    allow_3p_cookies: true,
    set_google_default: true,
    capture_preview: true,
    restore_session: true,
    transparent_proxy: false,
    portable_cookies: false,
    notes: null,
    user_data_dir: "/data/p1",
    sort_order: 0,
    current_config_version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("useUpdateProfileMutation cache write (t058 A24, AC-003)", () => {
  it("a stale in-flight detail GET resolving after save does not overwrite the saved values", async () => {
    const initial = profile();
    const saved = profile({ name: "Saved", current_config_version: 2 });
    const get = vi.fn(async () => initial);
    // The second GET hangs: it is the in-flight old request at save time.
    let releaseStale!: (value: ProfileResponse) => void;
    const stalePromise = new Promise<ProfileResponse>((resolve) => {
      releaseStale = resolve;
    });
    get.mockResolvedValueOnce(initial).mockReturnValueOnce(stalePromise);
    const update = vi.fn(async () => saved);
    const stub = {
      profiles: {
        get,
        update,
        list: vi.fn(async () => []),
      },
    } as unknown as ApiClient;

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(
      () => ({
        detail: useProfileQuery("p1", stub),
        updateMutation: useUpdateProfileMutation(stub),
      }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.detail.data).toEqual(initial));

    // Start the old GET and leave it in flight while the save runs.
    const refetch = queryClient.refetchQueries({
      queryKey: profileKeys.detail("p1"),
    });
    refetch.catch(() => undefined);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));

    await act(async () => {
      await result.current.updateMutation.mutateAsync({
        id: "p1",
        data: { name: "Saved" },
      });
    });
    await waitFor(() =>
      expect(
        queryClient.getQueryData<ProfileResponse>(profileKeys.detail("p1")),
      ).toEqual(saved),
    );

    // The stale GET finally resolves with the pre-save values.
    await act(async () => {
      releaseStale(initial);
      await new Promise((resolve) => setTimeout(resolve, 100));
    });

    expect(
      queryClient.getQueryData<ProfileResponse>(profileKeys.detail("p1")),
    ).toEqual(saved);
    // No detail refetch was triggered by the save either.
    expect(get).toHaveBeenCalledTimes(2);
  });
});
