import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "../../i18n";
import type { ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import type { ProfileResponse, ProfileRuntimeResponse } from "../../shared/api/types";
import { ProfileDetailPage } from "./ProfileDetailPage";

const BASE_PROFILE = {
  id: "p1",
  name: "Original",
  fingerprint_seed: 101,
  screen_width: 1920,
  screen_height: 1080,
  gpu_family: "auto",
  humanize: false,
  geoip: false,
  clipboard_sync: false,
  auto_launch: false,
  launch_args: [],
  extension_paths: [],
  current_config_version: 1,
  font_bundle: "none",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
} as unknown as ProfileResponse;

function runtime(overrides: Partial<ProfileRuntimeResponse>): ProfileRuntimeResponse {
  return {
    profile_id: "p1",
    desired_state: "stopped",
    observed_state: "stopped",
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  } as ProfileRuntimeResponse;
}

/**
 * Real hook wiring against an injected stub client (A22): the page, its
 * query/mutation hooks and the ApiClient boundary are exercised together;
 * no hook module is mocked.
 */
function makeStub() {
  const state = {
    profile: { ...BASE_PROFILE } as ProfileResponse,
    runtime: runtime({}),
  };
  const client = {
    profiles: {
      get: vi.fn(async () => state.profile),
      getRuntime: vi.fn(async () => state.runtime),
      update: vi.fn(
        async (_id: string, data: Record<string, unknown>) => {
          state.profile = { ...state.profile, ...data } as ProfileResponse;
          return state.profile;
        },
      ),
      delete: vi.fn(async () => undefined),
      duplicate: vi.fn(async () => state.profile),
      reset: vi.fn(async () => state.profile),
      stop: vi.fn(async () => {
        state.runtime = runtime({ observed_state: "stopped" });
        return state.runtime;
      }),
      setDesiredState: vi.fn(async () => {
        state.runtime = runtime({
          desired_state: "running",
          observed_state: "running",
        });
        return state.runtime;
      }),
      retrySearchDefaults: vi.fn(async () => state.runtime),
    },
  } as unknown as ApiClient & {
    profiles: { [K in keyof ApiClient["profiles"]]: ReturnType<typeof vi.fn> };
  };
  return { client, state };
}

let stub: ReturnType<typeof makeStub>;
let queryClient: QueryClient;

function renderPage() {
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ApiClientContext.Provider value={stub.client}>
          <MemoryRouter initialEntries={["/profiles/p1"]}>
            <Routes>
              <Route path="/profiles/:profileId" element={<ProfileDetailPage />} />
              <Route path="/" element={<div>dashboard</div>} />
            </Routes>
          </MemoryRouter>
        </ApiClientContext.Provider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("ProfileDetailPage", () => {
  beforeEach(() => {
    localStorage.clear();
    stub = makeStub();
  });

  it("does not overwrite unsaved edits when background data refreshes", async () => {
    renderPage();
    const input = (await screen.findByTestId(
      "profile-name-input",
    )) as HTMLInputElement;
    expect(input.value).toBe("Original");
    fireEvent.change(input, { target: { value: "Edited locally" } });

    // Simulate a background refresh delivering a newer server name.
    stub.state.profile = { ...stub.state.profile, name: "Server refreshed" };
    await act(async () => {
      await queryClient.invalidateQueries();
    });

    expect(
      (screen.getByTestId("profile-name-input") as HTMLInputElement).value,
    ).toBe("Edited locally");
  });

  it("echoes the saved font bundle and submits a changed one", async () => {
    stub.state.profile = {
      ...stub.state.profile,
      font_bundle: "wqy-zenhei",
    } as ProfileResponse;
    renderPage();
    const select = (await screen.findByTestId(
      "profile-font-bundle-select",
    )) as HTMLSelectElement;
    expect(select.value).toBe("wqy-zenhei");
    expect(Array.from(select.options).map((o) => o.value)).toEqual([
      "none",
      "wqy-microhei",
      "wqy-zenhei",
    ]);

    fireEvent.change(select, { target: { value: "wqy-microhei" } });
    fireEvent.submit(select.closest("form") as HTMLFormElement);
    await waitFor(() =>
      expect(stub.client.profiles.update).toHaveBeenCalledTimes(1),
    );
    const [, data] = stub.client.profiles.update.mock.calls[0] as [
      string,
      { font_bundle?: string },
    ];
    expect(data.font_bundle).toBe("wqy-microhei");

    // The save invalidates the profile query; the refetched server echo
    // drives the select.
    await waitFor(() =>
      expect(
        (screen.getByTestId("profile-font-bundle-select") as HTMLSelectElement)
          .value,
      ).toBe("wqy-microhei"),
    );
  });

  it("saves edited fields through the update mutation", async () => {
    renderPage();
    const input = (await screen.findByTestId(
      "profile-name-input",
    )) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Renamed" } });
    fireEvent.click(screen.getByTestId("profile-edit-submit"));
    await waitFor(() =>
      expect(stub.client.profiles.update).toHaveBeenCalledWith(
        "p1",
        expect.objectContaining({ name: "Renamed" }),
        expect.any(String),
      ),
    );
    expect(await screen.findByTestId("profile-save-success")).toBeTruthy();
  });

  it("deletes the profile after confirmation and navigates away", async () => {
    renderPage();
    await screen.findByTestId("profile-detail-page");
    const originalConfirm = window.confirm;
    window.confirm = () => true;
    try {
      fireEvent.click(screen.getByRole("button", { name: /delete/i }));
      await waitFor(() =>
        expect(stub.client.profiles.delete).toHaveBeenCalledWith(
          "p1",
          expect.any(String),
        ),
      );
      expect(await screen.findByText("dashboard")).toBeTruthy();
    } finally {
      window.confirm = originalConfirm;
    }
  });

  it("duplicates with the settings-only payload from the panel", async () => {
    renderPage();
    await screen.findByTestId("profile-detail-page");
    fireEvent.click(screen.getByTestId("profile-duplicate-button"));
    fireEvent.click(
      screen.getByRole("button", {
        name: "Duplicate settings and fingerprint only",
      }),
    );
    await waitFor(() =>
      expect(stub.client.profiles.duplicate).toHaveBeenCalledWith(
        "p1",
        { include_browser_state: false },
        expect.any(String),
      ),
    );
  });

  it("resets only after the panel confirmation", async () => {
    renderPage();
    await screen.findByTestId("profile-detail-page");
    fireEvent.click(screen.getByTestId("profile-reset-button"));
    const panel = screen.getByTestId("profile-reset-panel");
    expect(stub.client.profiles.reset).not.toHaveBeenCalled();
    fireEvent.click(within(panel).getByRole("button", { name: "Reset" }));
    await waitFor(() =>
      expect(stub.client.profiles.reset).toHaveBeenCalledWith(
        "p1",
        expect.any(String),
      ),
    );
  });

  it("applies pending display settings via stop then start", async () => {
    stub.state.runtime = runtime({
      desired_state: "running",
      observed_state: "running",
      config_version: 2,
    });
    renderPage();
    const applyBtn = await screen.findByTestId("profile-display-apply-btn");
    fireEvent.click(applyBtn);
    await waitFor(() =>
      expect(stub.client.profiles.setDesiredState).toHaveBeenCalled(),
    );
    const stopOrder = stub.client.profiles.stop.mock.invocationCallOrder[0]!;
    const startOrder =
      stub.client.profiles.setDesiredState.mock.invocationCallOrder[0]!;
    expect(stopOrder).toBeLessThan(startOrder);
    const stopKey = stub.client.profiles.stop.mock.calls[0]?.[1] as string;
    const startKey = stub.client.profiles.setDesiredState.mock
      .calls[0]?.[2] as string;
    expect(stopKey).not.toBe(startKey);
    expect(stopKey.replace(/:stop$/, "")).toBe(
      startKey.replace(/:start$/, ""),
    );
  });
});
