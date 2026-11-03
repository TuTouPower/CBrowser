import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "../../i18n";
import type { ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import type { ProfileResponse } from "../../shared/api/types";
import { ProfileAutomationPage } from "./ProfileAutomationPage";

const profile: ProfileResponse = {
  id: "p1",
  name: "Profile Alpha",
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
  tags: [],
  current_config_version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function makeStubClient() {
  /** Fresh stub per render at the ApiClient boundary (A22). */
  return {
    profiles: { get: vi.fn(async () => profile) },
    automation: {
      status: vi.fn(async (id: string) => ({
        profile_id: id,
        cdp_ws_path: `/api/v1/automation/profiles/${id}/cdp`,
        supervisor_configured: true,
        runtime_observed_state: "running",
        runtime_instance_id: "i1",
        token_header: "Authorization: Bearer <cbat_...>",
      })),
    },
  } as unknown as ApiClient;
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(
    [{ path: "/automation/:profileId", element: <ProfileAutomationPage /> }],
    { initialEntries: ["/automation/p1"] },
  );
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ApiClientContext.Provider value={makeStubClient()}>
          <RouterProvider router={router} />
        </ApiClientContext.Provider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("ProfileAutomationPage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders the authorized endpoint and runtime status on direct load", async () => {
    const view = renderPage();
    const endpoint = await view.findByTestId("automation-endpoint");
    expect(endpoint.textContent).toMatch(
      /^wss?:\/\/.+\/api\/v1\/automation\/profiles\/p1\/cdp$/,
    );
    expect(view.getByTestId("automation-runtime-state")).toHaveTextContent("running");
    expect(view.getByText("Configured")).toBeInTheDocument();
    expect(view.getByText(/Authorization: Bearer/)).toBeInTheDocument();
  });
});
