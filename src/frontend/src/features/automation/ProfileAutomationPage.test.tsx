import { beforeEach, describe, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "../../i18n";
import { defaultApiClient } from "../../shared/api/client";
import type { ProfileResponse } from "../../shared/api/types";
import { ProfileAutomationPage } from "./ProfileAutomationPage";

const profile = {
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
  tags: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
} as ProfileResponse;

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
        <RouterProvider router={router} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("ProfileAutomationPage", () => {
  beforeEach(() => {
    localStorage.clear();
    defaultApiClient.profiles.get = async () => profile;
    defaultApiClient.automation.status = async (id) => ({
      profile_id: id,
      cdp_ws_path: `/api/v1/automation/profiles/${id}/cdp`,
      supervisor_configured: true,
      runtime_observed_state: "running",
      runtime_instance_id: "i1",
      token_header: "Authorization: Bearer <cbat_...>",
    });
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
