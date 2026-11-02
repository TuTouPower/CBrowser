import { describe, it, expect, beforeEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, within, fireEvent, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { routes } from "./router";
import { defaultApiClient } from "../shared/api/client";
import { AuthProvider } from "../features/auth/useAuth";
import { I18nProvider } from "../i18n";

describe("Application Router & AC-001 Target Independence", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    localStorage.clear();

    // Mock API client methods
    defaultApiClient.auth.session = async () => ({
      authenticated: true,
      csrf_token: "mock-csrf-token",
    });

    defaultApiClient.profiles.list = async () => [
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
        tags: ["tag1"],
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
        tags: ["tag2"],
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "p3",
        name: "Profile Gamma",
        fingerprint_seed: 103,
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
      },
    ];

    defaultApiClient.profiles.get = async (id: string) => {
      const list = await defaultApiClient.profiles.list();
      const found = list.find((p) => p.id === id);
      if (!found) throw new Error("Not found");
      return found;
    };

    defaultApiClient.profiles.getRuntime = async (id: string) => ({
      profile_id: id,
      desired_state: "running",
      observed_state: "running",
      config_version: 1,
      failure_count: 0,
      restart_blocked: false,
      updated_at: "2026-01-01T00:00:00Z",
    });

    defaultApiClient.artifacts.list = async () => [];
    defaultApiClient.automation.status = async (id: string) => ({
      profile_id: id,
      cdp_ws_path: `/api/v1/automation/profiles/${id}/cdp`,
      supervisor_configured: true,
      runtime_observed_state: "running",
      runtime_instance_id: "i1",
      token_header: "Authorization: Bearer <cbat_...>",
    });
  });

  const renderWithRouter = (
    initialEntries: string[],
    { authenticated = true }: { authenticated?: boolean } = {},
  ) => {
    defaultApiClient.auth.session = async () => {
      if (!authenticated) {
        throw new Error("unauthenticated");
      }
      return { authenticated: true, csrf_token: "mock-csrf-token" };
    };
    const testQueryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const container = document.createElement("div");
    document.body.appendChild(container);
    const router = createMemoryRouter(routes, { initialEntries });
    const result = render(
      <QueryClientProvider client={testQueryClient}>
        <I18nProvider>
          <AuthProvider client={defaultApiClient}>
            <RouterProvider router={router} />
          </AuthProvider>
        </I18nProvider>
      </QueryClientProvider>,
      { container },
    );
    return { ...result, router, container, ...within(container) };
  };

  it("navigates to Plan 13.1 routes correctly", async () => {
    // 1. /login (unauthenticated visitors see the login page)
    const loginRender = renderWithRouter(["/login"], { authenticated: false });
    expect(await loginRender.findByTestId("login-page")).toBeInTheDocument();
    loginRender.unmount();

    // 2. /settings
    const settingsRender = renderWithRouter(["/settings"]);
    expect(await settingsRender.findByTestId("settings-page")).toBeInTheDocument();
    settingsRender.unmount();

    // 3. /profiles/new
    const newProfileRender = renderWithRouter(["/profiles/new"]);
    expect(await newProfileRender.findByTestId("profile-new-page")).toBeInTheDocument();
    newProfileRender.unmount();

    // 4. /profiles/:profileId
    const editProfileRender = renderWithRouter(["/profiles/p1"]);
    expect(await editProfileRender.findByTestId("profile-detail-page")).toBeInTheDocument();
    editProfileRender.unmount();

    // 5. /profiles/:profileId/files
    const filesRender = renderWithRouter(["/profiles/p1/files"]);
    expect(await filesRender.findByTestId("profile-files-page")).toBeInTheDocument();
    filesRender.unmount();

    // 6. /automation/:profileId
    const automationRender = renderWithRouter(["/automation/p1"]);
    expect(await automationRender.findByTestId("profile-automation-page")).toBeInTheDocument();
    automationRender.unmount();
  });

  it("AC-001: URL ?profileId= determines target, switching updates only that page URL, forbidden localStorage, two independent page instances do not interfere", async () => {
    // Instance A starts with ?profileId=p1
    const instanceA = renderWithRouter(["/?profileId=p1"]);
    await waitFor(() => {
      expect(instanceA.getByTestId("active-profile-header")).toHaveTextContent("Profile Alpha");
    });
    expect(instanceA.getByTestId("browser-session-mount")).toBeInTheDocument();

    // Instance B starts with ?profileId=p2
    const instanceB = renderWithRouter(["/?profileId=p2"]);
    await waitFor(() => {
      expect(instanceB.getByTestId("active-profile-header")).toHaveTextContent("Profile Beta");
    });

    // In Instance A, switch to Profile Gamma (p3)
    const gammaButtonInA = instanceA.getByTestId("profile-item-p3");
    fireEvent.click(gammaButtonInA);

    // Verify Instance A now targets p3
    await waitFor(() => {
      expect(instanceA.getByTestId("active-profile-header")).toHaveTextContent("Profile Gamma");
    });
    expect(instanceA.router.state.location.search).toBe("?profileId=p3");

    // Verify Instance B remains strictly targeting p2 (independent target isolation)
    expect(instanceB.getByTestId("active-profile-header")).toHaveTextContent("Profile Beta");
    expect(instanceB.router.state.location.search).toBe("?profileId=p2");

    // Strictly forbidden: localStorage.currentProfileId must NOT be used
    expect(localStorage.getItem("currentProfileId")).toBeNull();

    instanceA.unmount();
    instanceB.unmount();
  });

  it("offers duplicate and reset confirmations on the profile detail page", async () => {
    let resetCalled = false;
    defaultApiClient.profiles.getRuntime = async (id: string) => ({
      profile_id: id,
      desired_state: "stopped",
      observed_state: "stopped",
      config_version: 1,
      failure_count: 0,
      restart_blocked: false,
      updated_at: "2026-01-01T00:00:00Z",
    });
    defaultApiClient.profiles.reset = async () => {
      resetCalled = true;
      return (await defaultApiClient.profiles.get("p1"));
    };
    const view = renderWithRouter(["/profiles/p1"]);
    await view.findByTestId("profile-detail-page");

    let duplicatePayload: unknown = null;
    defaultApiClient.profiles.duplicate = async (_id, payload) => {
      duplicatePayload = payload;
      return await defaultApiClient.profiles.get("p1");
    };
    fireEvent.click(view.getByTestId("profile-duplicate-button"));
    expect(view.getByTestId("profile-duplicate-panel")).toHaveTextContent(
      "Duplicate profile",
    );
    fireEvent.click(view.getByRole("button", { name: "Duplicate settings and fingerprint only" }));
    await waitFor(() =>
      expect(duplicatePayload).toEqual({ include_browser_state: false }),
    );
    fireEvent.click(view.getByTestId("profile-reset-button"));
    expect(view.getByTestId("profile-reset-panel")).toHaveTextContent(/cookies/i);
    expect(view.getByTestId("profile-reset-panel")).toHaveTextContent(/history|bookmarks/i);
    expect(view.getByTestId("profile-reset-panel")).toHaveTextContent(/passwords|extensions/i);
    expect(resetCalled).toBe(false);
    fireEvent.click(
      within(view.getByTestId("profile-reset-panel")).getByRole("button", {
        name: "Reset",
      }),
    );
    await waitFor(() => expect(resetCalled).toBe(true));
    view.unmount();
  });

  it("AC-001: selecting a profile from a sub-route navigates to the session page", async () => {
    const settingsRender = renderWithRouter(["/settings"]);
    await settingsRender.findByTestId("settings-page");
    await settingsRender.findByTestId("profile-item-p2");
    fireEvent.click(settingsRender.getByTestId("profile-item-p2"));
    await waitFor(() => {
      expect(settingsRender.router.state.location.pathname).toBe("/");
      expect(settingsRender.router.state.location.search).toBe("?profileId=p2");
    });
    settingsRender.unmount();

    const detailRender = renderWithRouter(["/profiles/p1"]);
    await detailRender.findByTestId("profile-detail-page");
    await detailRender.findByTestId("profile-item-p2");
    fireEvent.click(detailRender.getByTestId("profile-item-p2"));
    await waitFor(() => {
      expect(detailRender.router.state.location.pathname).toBe("/");
      expect(detailRender.router.state.location.search).toBe("?profileId=p2");
    });
    detailRender.unmount();
  });
});
