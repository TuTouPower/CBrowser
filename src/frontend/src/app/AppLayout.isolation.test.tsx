import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "../i18n";
import { ApiClientContext } from "../shared/api/client_context";
import type { ApiClient } from "../shared/api/client";
import type {
  ProfileResponse,
  ProfileRuntimeResponse,
} from "../shared/api/types";
import { AuthProvider } from "../features/auth/useAuth";
import { AppLayout } from "./AppLayout";

/**
 * AC-003 (t025): the AppLayout header shares one layout instance across
 * profile switches, so its start/stop/apply mutation state must be
 * scoped to the profile the action targeted. A's apply error (including
 * the display-apply-error bar) and A's pending state must not leak onto
 * B, and A's late settle must not pollute B.
 */
function profile(id: string, name: string): ProfileResponse {
  return {
    id,
    name,
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
    human_preset: "default",
    font_bundle: "none",
    allow_3p_cookies: true,
    set_google_default: true,
    capture_preview: true,
    restore_session: true,
    transparent_proxy: false,
    portable_cookies: false,
    user_data_dir: `/data/${id}`,
    sort_order: 0,
    current_config_version: 2,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  } as ProfileResponse;
}

const PROFILES: Record<string, ProfileResponse> = {
  pA: profile("pA", "Alpha"),
  pB: profile("pB", "Beta"),
};

function makeStub() {
  const state: Record<string, { observed: string }> = {
    pA: { observed: "running" },
    pB: { observed: "running" },
  };
  const runtime = (id: string): ProfileRuntimeResponse =>
    ({
      profile_id: id,
      desired_state: state[id]!.observed === "stopped" ? "stopped" : "running",
      observed_state: state[id]!.observed,
      runtime_instance_id: `${id}-i1`,
      config_version: 1,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      last_coordinator_error: null,
      updated_at: "2026-01-01T00:00:00Z",
    }) as ProfileRuntimeResponse;
  const stop = vi.fn(async (id: string) => {
    state[id]!.observed = "stopped";
    return runtime(id);
  });
  const setDesiredState = vi.fn(async (id: string) => {
    state[id]!.observed = "running";
    return runtime(id);
  });
  const client = {
    setOnUnauthorized: vi.fn(),
    setCsrfToken: vi.fn(),
    auth: {
      session: vi.fn(async () => ({ authenticated: true, csrf_token: "t" })),
      login: vi.fn(),
      logout: vi.fn(async () => undefined),
    },
    profiles: {
      list: vi.fn(async () => Object.values(PROFILES)),
      get: vi.fn(async (id: string) => PROFILES[id]!),
      getRuntime: vi.fn(async (id: string) => runtime(id)),
      stop,
      setDesiredState,
    },
  } as unknown as ApiClient;
  return { client, stop, setDesiredState, state };
}

function renderLayout(client: ApiClient) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ApiClientContext.Provider value={client}>
          <AuthProvider client={client}>
            <MemoryRouter initialEntries={["/?profileId=pA"]}>
              <Routes>
                <Route element={<AppLayout />}>
                  <Route index element={<div>child</div>} />
                </Route>
              </Routes>
            </MemoryRouter>
          </AuthProvider>
        </ApiClientContext.Provider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

async function switchToB() {
  fireEvent.click(await screen.findByTestId("profile-item-pB"));
  await waitFor(() =>
    expect(screen.getByTestId("active-profile-header")).toHaveTextContent(
      "Beta",
    ),
  );
}

describe("AppLayout per-profile action isolation", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("does not show A's apply error bar on B", async () => {
    const stub = makeStub();
    stub.stop.mockImplementation(async () => {
      throw new Error("apply boom A");
    });
    renderLayout(stub.client);

    fireEvent.click(await screen.findByTestId("display-apply-restart-btn"));
    expect(await screen.findByTestId("display-apply-error")).toHaveTextContent(
      "apply boom A",
    );

    await switchToB();
    await waitFor(() =>
      expect(screen.queryByTestId("display-apply-error")).toBeNull(),
    );
    expect(screen.getByTestId("display-apply-restart-btn")).not.toBeDisabled();
  });

  it("does not disable B's apply while A's apply is pending, and A's late failure does not pollute B", async () => {
    const stub = makeStub();
    let rejectStop: ((err: Error) => void) | undefined;
    stub.stop.mockImplementation(
      () =>
        new Promise<ProfileRuntimeResponse>((_resolve, reject) => {
          rejectStop = reject;
        }),
    );
    renderLayout(stub.client);

    fireEvent.click(await screen.findByTestId("display-apply-restart-btn"));
    await waitFor(() =>
      expect(screen.getByTestId("display-apply-restart-btn")).toBeDisabled(),
    );

    await switchToB();
    await waitFor(() =>
      expect(screen.getByTestId("display-apply-restart-btn")).not.toBeDisabled(),
    );

    await act(async () => {
      rejectStop?.(new Error("late A failure"));
    });
    await waitFor(() =>
      expect(screen.queryByTestId("display-apply-error")).toBeNull(),
    );
  });
});
