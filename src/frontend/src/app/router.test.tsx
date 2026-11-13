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
import { SESS_ENTRY_PAGE, SESS_PAGE } from "../features/browser-session/session_keys";

const PROFILES: ProfileResponse[] = [
  {
    id: "p1",
    name: "Profile Alpha",
    display_number: 1,
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
    display_number: 1,
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
    display_number: 1,
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
    groups: { list: vi.fn(async () => []), create: vi.fn(async () => ({})) },
    proxies: { list: vi.fn(async () => []) },
    fontSets: { list: vi.fn(async () => ({ items: [], default_font_set_id: { windows: null, macos: null } })) },
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

    const list = renderWithRouter(["/"]);
    expect(await list.findByTestId("env-list-page")).toBeInTheDocument();
    list.unmount();

    for (const path of ["/session"]) {
      const view = renderWithRouter([path]);
      expect(await view.findByTestId(SESS_ENTRY_PAGE)).toBeInTheDocument();
      view.unmount();
    }

    const proxies = renderWithRouter(["/proxies"]);
    expect(await proxies.findByTestId("proxy-list-page")).toBeInTheDocument();
    proxies.unmount();

    const session = renderWithRouter(["/session/p1"]);
    expect(await session.findByTestId(SESS_PAGE)).toBeInTheDocument();
    session.unmount();

    for (const path of [
      "/profiles/p1/config",
      "/profiles/p1/files",
      "/profiles/p1/automation",
      "/profiles/p1/maintenance",
    ]) {
      const view = renderWithRouter([path]);
      expect(await view.findByTestId("profile-detail-view")).toBeInTheDocument();
      view.unmount();
    }

    const settings = renderWithRouter(["/settings"]);
    expect(await settings.findByTestId("settings-page")).toBeInTheDocument();
    settings.unmount();
  }, 20000);

  it("treats an unknown profileId as a normal detail route", async () => {
    const view = renderWithRouter(["/profiles/new"]);
    await waitFor(() =>
      expect(view.router.state.location.pathname).toBe(
        "/profiles/new/config",
      ),
    );
    expect(await view.findByTestId("profile-detail-view")).toBeInTheDocument();
    expect(view.queryByTestId("env-list-page")).not.toBeInTheDocument();
    expect(stubClient.profiles.get).toHaveBeenCalledWith("new");
    view.unmount();
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

  it("offers duplicate and reset actions on the maintenance tab", async () => {
    stubClient.profiles.getRuntime.mockImplementation(async (id: string) =>
      runtimeFor(id, "stopped"),
    );
    const view = renderWithRouter(["/profiles/p1/maintenance"]);
    expect(await view.findByTestId("profile-detail-view")).toBeInTheDocument();
    expect(await view.findByTestId("profile-maintenance-tab")).toBeInTheDocument();

    const duplicateSection = view.getByTestId("profile-maintenance-duplicate");
    const resetSection = view.getByTestId("profile-maintenance-reset");
    expect(resetSection).toHaveTextContent(/cookies/i);

    let duplicatePayload: unknown = null;
    stubClient.profiles.duplicate.mockImplementation(
      async (_id: string, payload: unknown) => {
        duplicatePayload = payload;
        return PROFILES[0];
      },
    );
    fireEvent.click(
      within(duplicateSection).getByRole("button", {
        name: "Configuration only",
      }),
    );
    await waitFor(() =>
      expect(duplicatePayload).toEqual({ include_browser_state: false }),
    );

    expect(stubClient.profiles.reset).not.toHaveBeenCalled();
    // Reset is two-step confirm (request → confirm); the confirm flow stays.
    fireEvent.click(
      within(resetSection).getByTestId("profile-maintenance-reset-request"),
    );
    expect(stubClient.profiles.reset).not.toHaveBeenCalled();
    fireEvent.click(
      within(resetSection).getByTestId("profile-maintenance-reset-confirm"),
    );
    await waitFor(() =>
      expect(stubClient.profiles.reset).toHaveBeenCalledWith(
        "p1",
        expect.any(String),
      ),
    );
    view.unmount();
  });
});
