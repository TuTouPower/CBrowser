import { describe, it, expect, beforeEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, within, fireEvent, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { routes } from "./router";
import type { ApiClient } from "../shared/api/client";
import { ApiClientContext } from "../shared/api/client_context";
import { AuthProvider } from "../features/auth/useAuth";
import { I18nProvider } from "../i18n";
import { ThemeProvider } from "../theme";
import { ToastProvider } from "../shared/ui";
import type { ProfileResponse, ProfileRuntimeResponse } from "../shared/api/types";

const PROFILES: ProfileResponse[] = [
  {
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
  {
    id: "p2",
    name: "Profile Beta",
    fingerprint_seed: 102,
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
  },
];

function runtimeFor(id: string, observed: string): ProfileRuntimeResponse {
  return {
    profile_id: id,
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

function makeStubClient() {
  return {
    setOnUnauthorized: vi.fn(),
    setCsrfToken: vi.fn(),
    request: vi.fn(async () => []),
    auth: {
      session: vi.fn(async () => ({
        authenticated: true,
        csrf_token: "mock-csrf-token",
      })),
      login: vi.fn(async () => ({ csrf_token: "mock-csrf-token" })),
      logout: vi.fn(async () => undefined),
    },
    health: { check: vi.fn(async () => undefined) },
    profiles: {
      list: vi.fn(async () => PROFILES),
      get: vi.fn(async (id: string) => {
        const found = PROFILES.find((p) => p.id === id);
        if (!found) throw new Error("Not found");
        return found;
      }),
      getRuntime: vi.fn(async (id: string) => runtimeFor(id, "running")),
      create: vi.fn(async () => PROFILES[0]),
      update: vi.fn(async () => PROFILES[0]),
      delete: vi.fn(async () => undefined),
      duplicate: vi.fn(async () => PROFILES[0]),
      reset: vi.fn(async () => PROFILES[0]),
      setDesiredState: vi.fn(async (id: string) => runtimeFor(id, "running")),
      stop: vi.fn(async (id: string) => runtimeFor(id, "stopped")),
      retrySearchDefaults: vi.fn(async () => runtimeFor("p1", "running")),
    },
    artifacts: {
      list: vi.fn(async () => []),
      upload: vi.fn(),
      delete: vi.fn(async () => undefined),
      downloadUrl: (profileId: string, artifactId: string) =>
        `/api/v1/profiles/${profileId}/artifacts/${artifactId}`,
    },
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
  } as unknown as ApiClient & {
    auth: { [K in keyof ApiClient["auth"]]: ReturnType<typeof vi.fn> };
    profiles: { [K in keyof ApiClient["profiles"]]: ReturnType<typeof vi.fn> };
  };
}

let stubClient: ReturnType<typeof makeStubClient>;

describe("Application Router (plan 5.1)", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    stubClient = makeStubClient();
  });

  const renderWithRouter = (
    initialEntries: string[],
    { authenticated = true }: { authenticated?: boolean } = {},
  ) => {
    stubClient.auth.session.mockImplementation(async () => {
      if (!authenticated) throw new Error("unauthenticated");
      return { authenticated: true, csrf_token: "mock-csrf-token" };
    });
    const testQueryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const container = document.createElement("div");
    document.body.appendChild(container);
    const router = createMemoryRouter(routes, { initialEntries });
    const result = render(
      <QueryClientProvider client={testQueryClient}>
        <I18nProvider>
          <ThemeProvider>
            <ToastProvider>
              <ApiClientContext.Provider value={stubClient as ApiClient}>
                <AuthProvider client={stubClient as ApiClient}>
                  <RouterProvider router={router} />
                </AuthProvider>
              </ApiClientContext.Provider>
            </ToastProvider>
          </ThemeProvider>
        </I18nProvider>
      </QueryClientProvider>,
      { container },
    );
    return { ...result, router, container, ...within(container) };
  };

  it("renders the plan 5.1 route table", async () => {
    const login = renderWithRouter(["/login"], { authenticated: false });
    expect(await login.findByTestId("login-page")).toBeInTheDocument();
    login.unmount();

    for (const path of ["/", "/session", "/proxies", "/profiles/p1/maintenance"]) {
      const view = renderWithRouter([path]);
      expect(await view.findByTestId("placeholder-page")).toBeInTheDocument();
      view.unmount();
    }

    const session = renderWithRouter(["/session/p1"]);
    expect(await session.findByTestId("browser-session-mount")).toBeInTheDocument();
    session.unmount();

    const config = renderWithRouter(["/profiles/p1/config"]);
    expect(await config.findByTestId("profile-detail-page")).toBeInTheDocument();
    config.unmount();

    const files = renderWithRouter(["/profiles/p1/files"]);
    expect(await files.findByTestId("profile-files-page")).toBeInTheDocument();
    files.unmount();

    const automation = renderWithRouter(["/profiles/p1/automation"]);
    expect(await automation.findByTestId("profile-automation-page")).toBeInTheDocument();
    automation.unmount();

    const settings = renderWithRouter(["/settings"]);
    expect(await settings.findByTestId("settings-page")).toBeInTheDocument();
    settings.unmount();
  });

  it("drops the legacy routes", async () => {
    const legacyNew = renderWithRouter(["/profiles/new"]);
    expect(await legacyNew.findByTestId("placeholder-page")).toBeInTheDocument();
    expect(legacyNew.queryByTestId("profile-new-page")).not.toBeInTheDocument();
    expect(legacyNew.router.state.location.pathname).toBe("/");
    legacyNew.unmount();

    const legacyAutomation = renderWithRouter(["/automation/p1"]);
    expect(await legacyAutomation.findByTestId("placeholder-page")).toBeInTheDocument();
    expect(legacyAutomation.queryByTestId("profile-automation-page")).not.toBeInTheDocument();
    legacyAutomation.unmount();

    const legacyTarget = renderWithRouter(["/?profileId=p1"]);
    expect(await legacyTarget.findByTestId("placeholder-page")).toBeInTheDocument();
    expect(legacyTarget.queryByTestId("active-profile-header")).not.toBeInTheDocument();
    legacyTarget.unmount();
  });

  it("renders navigation as real anchors", async () => {
    const view = renderWithRouter(["/"]);
    await view.findByTestId("sidebar");
    const links = view.container.querySelectorAll("nav a[href]");
    expect(links.length).toBeGreaterThanOrEqual(4);
    for (const link of links) {
      expect(link.getAttribute("href")).toBeTruthy();
    }
    view.unmount();
  });

  it("redirects /profiles/:profileId to the config tab", async () => {
    const view = renderWithRouter(["/profiles/p1"]);
    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe("/profiles/p1/config"),
    );
    view.unmount();
  });

  it("offers duplicate and reset confirmations on the config page", async () => {
    let resetCalled = false;
    stubClient.profiles.getRuntime.mockImplementation(async (id: string) =>
      runtimeFor(id, "stopped"),
    );
    stubClient.profiles.reset.mockImplementation(async () => {
      resetCalled = true;
      return PROFILES[0];
    });
    const view = renderWithRouter(["/profiles/p1/config"]);
    await view.findByTestId("profile-detail-page");

    let duplicatePayload: unknown = null;
    stubClient.profiles.duplicate.mockImplementation(
      async (_id: string, payload: unknown) => {
        duplicatePayload = payload;
        return PROFILES[0];
      },
    );
    fireEvent.click(view.getByTestId("profile-duplicate-button"));
    expect(view.getByTestId("profile-duplicate-panel")).toHaveTextContent(
      "Duplicate profile",
    );
    fireEvent.click(view.getByRole("button", { name: "Duplicate settings and fingerprint only" }));
    await waitFor(() =>
      expect(duplicatePayload).toEqual({ include_browser_state: false }),
    );
    await view.findByTestId("profile-detail-page");
    fireEvent.click(view.getByTestId("profile-reset-button"));
    expect(view.getByTestId("profile-reset-panel")).toHaveTextContent(/cookies/i);
    expect(resetCalled).toBe(false);
    fireEvent.click(
      within(view.getByTestId("profile-reset-panel")).getByRole("button", {
        name: "Reset",
      }),
    );
    await waitFor(() => expect(resetCalled).toBe(true));
    view.unmount();
  });
});
