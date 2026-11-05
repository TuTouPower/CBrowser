import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import {
  MemoryRouter,
  Routes,
  Route,
  useNavigate,
  type NavigateFunction,
} from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "../../i18n";
import type { ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import type {
  ProfileResponse,
  ProfileRuntimeResponse,
} from "../../shared/api/types";
import { ProfileDetailPage } from "./ProfileDetailPage";

/**
 * AC-003 (t025): ProfileDetailPage keeps its mutation hooks mounted
 * across /profiles/:profileId param changes, so apply error/pending must
 * be scoped to the profile the action targeted.
 */
function profile(id: string, name: string): ProfileResponse {
  return {
    id,
    name,
    fingerprint_seed: 101,
    proxy: "",
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
    current_config_version: 2,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  } as unknown as ProfileResponse;
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
      search_defaults: null,
      updated_at: "2026-01-01T00:00:00Z",
    }) as ProfileRuntimeResponse;
  const update = vi.fn(async (id: string) => PROFILES[id]!);
  const stop = vi.fn(async (id: string) => {
    state[id]!.observed = "stopped";
    return runtime(id);
  });
  const setDesiredState = vi.fn(async (id: string) => {
    state[id]!.observed = "running";
    return runtime(id);
  });
  const client = {
    profiles: {
      get: vi.fn(async (id: string) => PROFILES[id]!),
      getRuntime: vi.fn(async (id: string) => runtime(id)),
      update,
      delete: vi.fn(async () => undefined),
      duplicate: vi.fn(async (id: string) => PROFILES[id]!),
      reset: vi.fn(async (id: string) => PROFILES[id]!),
      stop,
      setDesiredState,
      retrySearchDefaults: vi.fn(async (id: string) => runtime(id)),
    },
  } as unknown as ApiClient;
  return { client, stop, update };
}

let navigateFn: NavigateFunction;
function NavCapture() {
  navigateFn = useNavigate();
  return null;
}

function renderPage(client: ApiClient) {
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
          <MemoryRouter initialEntries={["/profiles/pA"]}>
            <NavCapture />
            <Routes>
              <Route
                path="/profiles/:profileId"
                element={<ProfileDetailPage />}
              />
            </Routes>
          </MemoryRouter>
        </ApiClientContext.Provider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("ProfileDetailPage per-profile action isolation", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("does not show A's apply error on B", async () => {
    const stub = makeStub();
    stub.stop.mockImplementation(async () => {
      throw new Error("apply boom A");
    });
    renderPage(stub.client);

    fireEvent.click(await screen.findByTestId("profile-display-apply-btn"));
    expect(
      await screen.findByTestId("profile-display-apply-error"),
    ).toHaveTextContent("apply boom A");

    act(() => navigateFn("/profiles/pB"));
    await waitFor(() =>
      expect(screen.getByTestId("profile-name-input")).toHaveValue("Beta"),
    );
    await waitFor(() =>
      expect(screen.queryByTestId("profile-display-apply-error")).toBeNull(),
    );
    expect(
      screen.getByTestId("profile-display-apply-btn"),
    ).not.toBeDisabled();
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
    renderPage(stub.client);

    fireEvent.click(await screen.findByTestId("profile-display-apply-btn"));
    await waitFor(() =>
      expect(screen.getByTestId("profile-display-apply-btn")).toBeDisabled(),
    );

    act(() => navigateFn("/profiles/pB"));
    await waitFor(() =>
      expect(screen.getByTestId("profile-name-input")).toHaveValue("Beta"),
    );
    await waitFor(() =>
      expect(
        screen.getByTestId("profile-display-apply-btn"),
      ).not.toBeDisabled(),
    );

    await act(async () => {
      rejectStop?.(new Error("late A failure"));
    });
    await waitFor(() =>
      expect(screen.queryByTestId("profile-display-apply-error")).toBeNull(),
    );
  });

  it("does not show A's late update failure on B (local banner channel)", async () => {
    const stub = makeStub();
    let rejectUpdate: ((err: Error) => void) | undefined;
    stub.update.mockImplementation(
      () =>
        new Promise<ProfileResponse>((_resolve, reject) => {
          rejectUpdate = reject;
        }),
    );
    renderPage(stub.client);

    fireEvent.click(await screen.findByTestId("profile-edit-submit"));
    await waitFor(() => expect(stub.update).toHaveBeenCalled());

    act(() => navigateFn("/profiles/pB"));
    await waitFor(() =>
      expect(screen.getByTestId("profile-name-input")).toHaveValue("Beta"),
    );

    await act(async () => {
      rejectUpdate?.(new Error("late update failed A"));
    });
    // Negative assertion: give the late rejection a chance to land,
    // then require that no banner for A appears on B.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByText("late update failed A")).toBeNull();
  });

  it("does not show A's late update success on B (local banner channel)", async () => {
    const stub = makeStub();
    let resolveUpdate: ((value: ProfileResponse) => void) | undefined;
    stub.update.mockImplementation(
      () =>
        new Promise<ProfileResponse>((resolve) => {
          resolveUpdate = resolve;
        }),
    );
    renderPage(stub.client);

    fireEvent.click(await screen.findByTestId("profile-edit-submit"));
    await waitFor(() => expect(stub.update).toHaveBeenCalled());

    act(() => navigateFn("/profiles/pB"));
    await waitFor(() =>
      expect(screen.getByTestId("profile-name-input")).toHaveValue("Beta"),
    );

    await act(async () => {
      resolveUpdate?.(PROFILES.pA!);
    });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByTestId("profile-save-success")).toBeNull();
  });
});
