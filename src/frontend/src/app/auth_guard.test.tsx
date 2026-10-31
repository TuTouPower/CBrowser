import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { QueryClient } from "@tanstack/react-query";
import { AppProviders } from "./providers";
import { routes } from "./router";
import { ApiError, defaultApiClient } from "../shared/api/client";
import type { ProfileEventsClient } from "../shared/api/sse";
import type { ProfileResponse, ProfileRuntimeResponse } from "../shared/api/types";
import { sanitizeNextPath } from "../features/auth/redirect";

const PROFILE: ProfileResponse = {
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
};

const RUNTIME: ProfileRuntimeResponse = {
  profile_id: "p1",
  desired_state: "stopped",
  observed_state: "stopped",
  config_version: 1,
  failure_count: 0,
  restart_blocked: false,
  updated_at: "2026-01-01T00:00:00Z",
};

interface MockedApi {
  state: { authenticated: boolean };
  expireOnNextMutation: () => void;
  triggerUnauthorized: () => void;
}

function makeFakeSse(): ProfileEventsClient & {
  start: ReturnType<typeof vi.fn>;
  stop: ReturnType<typeof vi.fn>;
} {
  return {
    start: vi.fn(),
    stop: vi.fn(),
    onEvent: vi.fn(() => () => {}),
    onError: vi.fn(() => () => {}),
  } as unknown as ProfileEventsClient & {
    start: ReturnType<typeof vi.fn>;
    stop: ReturnType<typeof vi.fn>;
  };
}

function mockApi(authenticated: boolean): MockedApi {
  const state = { authenticated };
  let unauthorized: (() => void) | undefined;
  let expireNextMutation = false;

  defaultApiClient.setOnUnauthorized = (callback?: () => void) => {
    unauthorized = callback;
  };

  defaultApiClient.auth.session = vi.fn(async () => {
    if (!state.authenticated) {
      throw new ApiError("Authentication required", 401);
    }
    return { authenticated: true, csrf_token: "mock-csrf-token" };
  });

  defaultApiClient.auth.login = vi.fn(async () => {
    state.authenticated = true;
    return { csrf_token: "mock-csrf-token" };
  });

  defaultApiClient.auth.logout = vi.fn(async () => {
    state.authenticated = false;
    defaultApiClient.setCsrfToken(null);
  });

  defaultApiClient.profiles.list = vi.fn(async () => [PROFILE]);
  defaultApiClient.profiles.get = vi.fn(async () => PROFILE);
  defaultApiClient.profiles.getRuntime = vi.fn(async () => RUNTIME);
  defaultApiClient.profiles.stop = vi.fn(async () => RUNTIME);
  defaultApiClient.profiles.setDesiredState = vi.fn(async () => {
    if (expireNextMutation) {
      state.authenticated = false;
      unauthorized?.();
      throw new ApiError("Invalid or expired session", 401);
    }
    return RUNTIME;
  });

  return {
    state,
    expireOnNextMutation: () => {
      expireNextMutation = true;
    },
    triggerUnauthorized: () => unauthorized?.(),
  };
}

function renderApp(initialEntries: string[], sseClient = makeFakeSse()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(routes, { initialEntries });
  render(
    <AppProviders queryClient={queryClient} sseClient={sseClient}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { router, sseClient };
}

describe("auth guard and session expiry", () => {
  beforeEach(() => {
    localStorage.clear();
    mockApi(false);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("redirects unauthenticated app routes to /login and preserves the target", async () => {
    const api = mockApi(false);
    const { router } = renderApp(["/?profileId=p1"]);

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(new URLSearchParams(router.state.location.search).get("next")).toBe(
      "/?profileId=p1",
    );
    expect(await screen.findByTestId("login-page")).toBeInTheDocument();
    expect(api.state.authenticated).toBe(false);
    expect(defaultApiClient.profiles.list).not.toHaveBeenCalled();
  });

  it("shows a loading state and issues no business requests while the session check is pending", async () => {
    defaultApiClient.auth.session = () => new Promise(() => {});
    const sseClient = makeFakeSse();
    renderApp(["/?profileId=p1"], sseClient);

    expect(await screen.findByTestId("auth-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("browser-session-mount")).not.toBeInTheDocument();
    expect(screen.queryByTestId("active-profile-header")).not.toBeInTheDocument();
    expect(defaultApiClient.profiles.list).not.toHaveBeenCalled();
    expect(sseClient.start).not.toHaveBeenCalled();
  });

  it("renders the app and starts SSE only after authentication", async () => {
    mockApi(true);
    const sseClient = makeFakeSse();
    renderApp(["/?profileId=p1"], sseClient);

    expect(
      await screen.findByTestId("active-profile-header"),
    ).toHaveTextContent("Profile Alpha");
    expect(sseClient.start).toHaveBeenCalledTimes(1);
  });

  it("clears auth, stops SSE and redirects to /login preserving the target on API 401", async () => {
    const api = mockApi(true);
    const sseClient = makeFakeSse();
    const { router } = renderApp(["/?profileId=p1"], sseClient);

    await screen.findByTestId("active-profile-header");
    expect(sseClient.start).toHaveBeenCalled();

    api.expireOnNextMutation();
    fireEvent.click(screen.getByTestId("header-launch-btn"));

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(new URLSearchParams(router.state.location.search).get("next")).toBe(
      "/?profileId=p1",
    );
    expect(await screen.findByTestId("login-page")).toBeInTheDocument();
    expect(sseClient.stop).toHaveBeenCalled();
  });

  it("logs out through useAuth, stops SSE and redirects to /login", async () => {
    const api = mockApi(true);
    const sseClient = makeFakeSse();
    const { router } = renderApp(["/?profileId=p1"], sseClient);

    await screen.findByTestId("active-profile-header");
    fireEvent.click(screen.getByTitle("Log out"));

    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
    expect(api.state.authenticated).toBe(false);
    expect(defaultApiClient.auth.logout).toHaveBeenCalled();
    expect(sseClient.stop).toHaveBeenCalled();
  });

  it("authenticates through AuthProvider and returns to the original target", async () => {
    const api = mockApi(false);
    const password = globalThis.crypto.randomUUID();
    const { router } = renderApp(["/login?next=%2F%3FprofileId%3Dp1"]);

    await screen.findByTestId("login-page");
    fireEvent.change(screen.getByTestId("login-password"), {
      target: { value: password },
    });
    fireEvent.click(screen.getByTestId("login-submit"));

    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
    expect(router.state.location.search).toBe("?profileId=p1");
    expect(api.state.authenticated).toBe(true);
    expect(defaultApiClient.auth.login).toHaveBeenCalledWith({ password });
    expect(await screen.findByTestId("active-profile-header")).toHaveTextContent(
      "Profile Alpha",
    );
  });

  it("redirects authenticated visitors away from /login to the target or root", async () => {
    mockApi(true);
    const withTarget = renderApp(["/login?next=%2Fsettings"]);
    await waitFor(() =>
      expect(withTarget.router.state.location.pathname).toBe("/settings"),
    );
    cleanup();

    const withoutTarget = renderApp(["/login"]);
    await waitFor(() =>
      expect(withoutTarget.router.state.location.pathname).toBe("/"),
    );
  });

  it("rejects open redirect targets", async () => {
    const hostile = [
      "//evil.example",
      "///evil.example",
      "/\\evil.example",
      "\\\\evil.example",
      "https://evil.example",
      "javascript:alert(1)",
    ];
    for (const target of hostile) {
      expect(sanitizeNextPath(target)).toBeNull();
    }
    expect(sanitizeNextPath("/?profileId=p1")).toBe("/?profileId=p1");
    expect(sanitizeNextPath("/settings")).toBe("/settings");
  });

  it("ignores an open redirect next value after login", async () => {
    mockApi(false);
    const password = globalThis.crypto.randomUUID();
    const { router } = renderApp(["/login?next=%2F%2Fevil.example"]);

    await screen.findByTestId("login-page");
    fireEvent.change(screen.getByTestId("login-password"), {
      target: { value: password },
    });
    fireEvent.click(screen.getByTestId("login-submit"));

    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
    expect(router.state.location.pathname).not.toContain("evil.example");
  });
});
