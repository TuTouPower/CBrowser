import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "../../i18n";
import { ApiError, type ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import type { ProfileResponse, ProfileRuntimeResponse } from "../../shared/api/types";
import { BrowserSessionPage } from "./BrowserSessionPage";

const PROFILE: ProfileResponse = {
  id: "p1",
  name: "Profile One",
  fingerprint_seed: 101,
  screen_width: 1920,
  screen_height: 1080,
  gpu_family: "auto",
  humanize: false,
  geoip: false,
  clipboard_sync: true,
  auto_launch: false,
  launch_args: [],
  extension_paths: [],
  tags: [],
  human_preset: "default",
  font_bundle: "none",
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
};

function runtime(observed: string): ProfileRuntimeResponse {
  return {
    profile_id: "p1",
    desired_state: observed === "running" ? "running" : "stopped",
    observed_state: observed,
    runtime_instance_id: null,
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    last_exit_event_id: null,
    updated_at: "2026-01-01T00:00:00Z",
  } as ProfileRuntimeResponse;
}

/**
 * Real hook wiring against an injected stub client (A22): no hook module
 * is mocked, so these tests exercise the page, the query/mutation hooks
 * and the ApiClient boundary together.
 */
function makeStub() {
  const state = { observed: "stopped" };
  const client = {
    profiles: {
      get: vi.fn(async () => PROFILE),
      getRuntime: vi.fn(async () => runtime(state.observed)),
      setDesiredState: vi.fn(async () => {
        state.observed = "running";
        return runtime("running");
      }),
    },
  } as unknown as ApiClient & {
    profiles: {
      get: ReturnType<typeof vi.fn>;
      getRuntime: ReturnType<typeof vi.fn>;
      setDesiredState: ReturnType<typeof vi.fn>;
    };
  };
  return { client, state };
}

let stub: ReturnType<typeof makeStub>;

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ApiClientContext.Provider value={stub.client}>
          <MemoryRouter initialEntries={["/?profileId=p1"]}>
            <BrowserSessionPage />
          </MemoryRouter>
        </ApiClientContext.Provider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("BrowserSessionPage", () => {
  beforeEach(() => {
    localStorage.clear();
    stub = makeStub();
  });

  it("mounts the session view when the runtime is running", async () => {
    stub.state.observed = "running";
    renderPage();
    expect(await screen.findByTestId("browser-session-mount")).toBeTruthy();
  });

  it("launches a stopped profile and mounts the session once it runs", async () => {
    renderPage();
    const launch = await screen.findByTestId("session-launch-btn");
    fireEvent.click(launch);
    await waitFor(() =>
      expect(stub.client.profiles.setDesiredState).toHaveBeenCalledWith(
        "p1",
        "running",
        expect.any(String),
      ),
    );
    expect(await screen.findByTestId("browser-session-mount")).toBeTruthy();
  });

  it("shows a start error instead of swallowing the mutation failure", async () => {
    stub.client.profiles.setDesiredState.mockRejectedValue(
      new Error("container start failed"),
    );
    renderPage();
    const launch = await screen.findByTestId("session-launch-btn");
    fireEvent.click(launch);
    const error = await screen.findByTestId("session-start-error");
    expect(error.textContent).toContain("container start failed");
  });

  it("shows profile-not-found only for a real 404 (A17)", async () => {
    stub.client.profiles.get.mockRejectedValue(
      new ApiError("Profile not found", 404),
    );
    renderPage();
    expect(await screen.findByText("Profile not found.")).toBeTruthy();
    expect(screen.queryByTestId("session-load-error")).toBeNull();
  });

  it("shows a load error with retry when the profile request fails (A17)", async () => {
    stub.client.profiles.get
      .mockRejectedValueOnce(new ApiError("boom", 500))
      .mockResolvedValue(PROFILE);
    renderPage();
    expect(await screen.findByTestId("session-load-error")).toBeTruthy();
    // A failed load must not be presented as a stopped profile.
    expect(screen.queryByTestId("session-runtime-not-ready")).toBeNull();
    fireEvent.click(screen.getByTestId("session-load-retry"));
    expect(await screen.findByTestId("session-runtime-not-ready")).toBeTruthy();
    expect(stub.client.profiles.get).toHaveBeenCalledTimes(2);
  });

  it("shows the loading state while requests are pending (A17)", async () => {
    stub.client.profiles.get.mockImplementation(
      () => new Promise(() => {}),
    );
    renderPage();
    expect(await screen.findByText("Loading...")).toBeTruthy();
    expect(screen.queryByTestId("session-runtime-not-ready")).toBeNull();
    expect(screen.queryByTestId("session-load-error")).toBeNull();
    expect(screen.queryByTestId("browser-session-mount")).toBeNull();
  });

  it("retries only the runtime query from the runtime error branch (A17)", async () => {
    stub.client.profiles.getRuntime
      .mockRejectedValueOnce(new ApiError("runtime unavailable", 500))
      .mockResolvedValue(runtime("stopped"));
    renderPage();
    expect(await screen.findByTestId("session-load-error")).toBeTruthy();
    fireEvent.click(screen.getByTestId("session-load-retry"));
    expect(await screen.findByTestId("session-runtime-not-ready")).toBeTruthy();
    expect(stub.client.profiles.getRuntime).toHaveBeenCalledTimes(2);
    expect(stub.client.profiles.get).toHaveBeenCalledTimes(1);
  });

  it("shows a load error when the runtime request fails instead of treating it as stopped (A17)", async () => {
    stub.client.profiles.getRuntime.mockRejectedValue(
      new ApiError("runtime unavailable", 500),
    );
    renderPage();
    expect(await screen.findByTestId("session-load-error")).toBeTruthy();
    expect(screen.queryByTestId("session-runtime-not-ready")).toBeNull();
    expect(screen.queryByTestId("browser-session-mount")).toBeNull();
  });
});
