import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "../../i18n";
import type { ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import type { ProfileResponse, ProfileRuntimeResponse } from "../../shared/api/types";
import { ProfileDetailPage } from "./ProfileDetailPage";

const PROFILE = {
  id: "p1",
  name: "Original",
  proxy: "",
  screen_width: 1920,
  screen_height: 1080,
  tags: [],
  current_config_version: 1,
} as unknown as ProfileResponse;

function runtimeWith(searchDefaultsState: string): ProfileRuntimeResponse {
  return {
    profile_id: "p1",
    desired_state: "running",
    observed_state: "running",
    runtime_instance_id: "inst_1",
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    last_exit_event_id: null,
    updated_at: "2026-11-04T00:00:00Z",
    search_defaults: {
      state: searchDefaultsState,
      error_kind: searchDefaultsState === "failed" ? "timeout" : null,
      runtime_instance_id: "inst_1",
      request_id: null,
      updated_at: "2026-11-04T00:00:00Z",
    },
  } as unknown as ProfileRuntimeResponse;
}

/**
 * Real hook wiring against an injected stub client (A22); the runtime
 * payload uses the full generated shape including search_defaults.
 */
function makeStub(searchDefaultsState: string) {
  const runtime = runtimeWith(searchDefaultsState);
  const client = {
    profiles: {
      get: vi.fn(async () => PROFILE),
      getRuntime: vi.fn(async () => runtime),
      update: vi.fn(async () => PROFILE),
      delete: vi.fn(async () => undefined),
      duplicate: vi.fn(async () => PROFILE),
      reset: vi.fn(async () => PROFILE),
      retrySearchDefaults: vi.fn(async () => runtime),
    },
  } as unknown as ApiClient & {
    profiles: { retrySearchDefaults: ReturnType<typeof vi.fn> };
  };
  return client;
}

let stub: ReturnType<typeof makeStub>;

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ApiClientContext.Provider value={stub}>
          <MemoryRouter initialEntries={["/profiles/p1"]}>
            <Routes>
              <Route path="/profiles/:profileId" element={<ProfileDetailPage />} />
            </Routes>
          </MemoryRouter>
        </ApiClientContext.Provider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("ProfileDetailPage search defaults (A55)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows an independent failure notice with a retry action", async () => {
    stub = makeStub("failed");
    renderPage();
    const panel = await screen.findByTestId("search-defaults-failed");
    const button = panel.querySelector("button");
    expect(button).toBeTruthy();
    fireEvent.click(button as HTMLButtonElement);
    await waitFor(() =>
      expect(stub.profiles.retrySearchDefaults).toHaveBeenCalledWith(
        "p1",
        expect.any(String),
      ),
    );
  });

  it("shows no notice when search defaults applied", async () => {
    stub = makeStub("applied");
    renderPage();
    await screen.findByTestId("profile-detail-page");
    expect(screen.queryByTestId("search-defaults-failed")).toBeNull();
  });
});
