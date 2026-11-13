import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";
import type {
  ProfileResponse,
  ProfileRuntimeResponse,
} from "../../shared/api/types";
import {
  ProfileEventsClient,
  type ProfilePreviewEvent,
} from "../../shared/api/sse";
import { profileKeys, useProfileEventsSync } from "./useProfilesQuery";

const profile: ProfileResponse = {
  id: "p1",
  name: "P",
  display_number: 1,
  fingerprint_seed: 1,
  screen_width: 1920,
  screen_height: 1080,
  gpu_family: "auto",
  humanize: false,
  human_preset: "default",
  geoip: false,
  clipboard_sync: false,
  auto_launch: false,
  launch_args: [],
  extension_paths: [],
  allow_3p_cookies: true,
  set_google_default: true,
  capture_preview: true,
  restore_session: true,
  transparent_proxy: false,
  portable_cookies: false,
  user_data_dir: "/data/p1",
  sort_order: 0,
  current_config_version: 1,
  created_at: "2026-11-12T00:00:00Z",
  updated_at: "2026-11-12T00:00:00Z",
};
const runtime: ProfileRuntimeResponse = {
  profile_id: "p1",
  display_number: 1,
  desired_state: "running",
  observed_state: "running",
  runtime_instance_id: "i",
  config_version: 1,
  failure_count: 0,
  restart_blocked: false,
  last_exit_event_id: null,
  updated_at: "2026-11-12T00:00:00Z",
  preview_captured_at: "2026-11-12T00:00:10Z",
};

function setup() {
  const query = new QueryClient();
  query.setQueryData(profileKeys.runtime("p1"), runtime);
  const sse = new ProfileEventsClient();
  let listener: ((event: ProfilePreviewEvent) => void) | undefined;
  sse.onPreviewEvent = (callback) => {
    listener = callback;
    return () => {
      listener = undefined;
    };
  };
  sse.start = () => {};
  sse.stop = () => {};
  sse.onEvent = () => () => {};
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: query }, children);
  const hook = renderHook(() => useProfileEventsSync(sse), { wrapper });
  return {
    query,
    hook,
    emit: (captured_at: string) =>
      act(() =>
        listener?.({ event: "profile_preview", profile_id: "p1", captured_at }),
      ),
  };
}

describe("preview SSE privacy and monotonicity", () => {
  it("ignores events with no cached permission or a disabled detail overriding stale enabled list", () => {
    const { query, hook, emit } = setup();
    emit("2026-11-12T00:00:20Z");
    expect(query.getQueryData(profileKeys.runtime("p1"))).toEqual(runtime);
    query.setQueryData(profileKeys.lists(), [profile]);
    query.setQueryData(profileKeys.detail("p1"), {
      ...profile,
      capture_preview: false,
    });
    emit("2026-11-12T00:00:20Z");
    expect(query.getQueryData(profileKeys.runtime("p1"))).toEqual(runtime);
    query.setQueryData(profileKeys.detail("p1"), profile);
    query.setQueryData(profileKeys.lists(), [
      { ...profile, capture_preview: false },
    ]);
    emit("2026-11-12T00:00:25Z");
    expect(query.getQueryData(profileKeys.runtime("p1"))).toEqual(runtime);
    hook.unmount();
  });
  it("uses cached list permission and compares instants including differing offsets", () => {
    const { query, hook, emit } = setup();
    query.setQueryData(profileKeys.lists(), [profile]);
    emit("2026-11-12T08:00:05+08:00");
    emit("invalid");
    expect(query.getQueryData(profileKeys.runtime("p1"))).toEqual(runtime);
    emit("2026-11-12T00:00:20Z");
    expect(
      query.getQueryData<ProfileRuntimeResponse>(profileKeys.runtime("p1"))
        ?.preview_captured_at,
    ).toBe("2026-11-12T00:00:20Z");
    query.setQueryData(profileKeys.detail("p1"), {
      ...profile,
      capture_preview: false,
    });
    query.setQueryData(profileKeys.runtime("p1"), {
      ...runtime,
      preview_captured_at: null,
    });
    emit("2026-11-12T00:00:30Z");
    expect(
      query.getQueryData<ProfileRuntimeResponse>(profileKeys.runtime("p1"))
        ?.preview_captured_at,
    ).toBeNull();
    hook.unmount();
  });
});
