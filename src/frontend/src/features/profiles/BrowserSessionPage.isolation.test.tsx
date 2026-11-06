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
import { BrowserSessionPage } from "./BrowserSessionPage";

/**
 * AC-003 (t025): session action state is scoped per Profile. An error or
 * pending launch for Profile A must not surface on Profile B after
 * switching, and A's late settle must not pollute B's view.
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
    clipboard_sync: true,
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
    user_data_dir: `/data/${id}`,
    sort_order: 0,
    current_config_version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  } as ProfileResponse;
}

function runtime(id: string): ProfileRuntimeResponse {
  return {
    profile_id: id,
    desired_state: "stopped",
    observed_state: "stopped",
    runtime_instance_id: null,
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    last_exit_event_id: null,
    last_coordinator_error: null,
    updated_at: "2026-01-01T00:00:00Z",
  } as ProfileRuntimeResponse;
}

const PROFILES: Record<string, ProfileResponse> = {
  pA: profile("pA", "Alpha"),
  pB: profile("pB", "Beta"),
};

function makeStub() {
  const setDesiredState = vi.fn(
    async (id: string): Promise<ProfileRuntimeResponse> => ({
      ...runtime(id),
      desired_state: "running",
      observed_state: "running",
    }),
  );
  const client = {
    profiles: {
      get: vi.fn(async (id: string) => PROFILES[id]!),
      getRuntime: vi.fn(async (id: string) => runtime(id)),
      setDesiredState,
    },
  } as unknown as ApiClient;
  return { client, setDesiredState };
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
          <MemoryRouter initialEntries={["/session/pA"]}>
            <NavCapture />
            <Routes>
              <Route path="/session/:profileId" element={<BrowserSessionPage />} />
            </Routes>
          </MemoryRouter>
        </ApiClientContext.Provider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("BrowserSessionPage per-profile action isolation", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("does not show A's launch error on B", async () => {
    const { client, setDesiredState } = makeStub();
    setDesiredState.mockImplementation(async (id: string) => {
      if (id === "pA") throw new Error("launch failed A");
      return { ...runtime(id), observed_state: "running" };
    });
    renderPage(client);

    fireEvent.click(await screen.findByTestId("session-launch-btn"));
    expect(await screen.findByTestId("session-start-error")).toHaveTextContent(
      "launch failed A",
    );

    act(() => navigateFn("/session/pB"));
    expect(await screen.findByText("Beta")).toBeTruthy();
    await waitFor(() =>
      expect(screen.queryByTestId("session-start-error")).toBeNull(),
    );
  });

  it("does not disable B's launch while A's launch is pending, and A's late failure does not pollute B", async () => {
    const { client, setDesiredState } = makeStub();
    let rejectA: ((err: Error) => void) | undefined;
    setDesiredState.mockImplementation((id: string) => {
      if (id === "pA") {
        return new Promise<ProfileRuntimeResponse>((_resolve, reject) => {
          rejectA = reject;
        });
      }
      return Promise.resolve({ ...runtime(id), observed_state: "running" });
    });
    renderPage(client);

    fireEvent.click(await screen.findByTestId("session-launch-btn"));
    await waitFor(() =>
      expect(screen.getByTestId("session-launch-btn")).toBeDisabled(),
    );

    act(() => navigateFn("/session/pB"));
    expect(await screen.findByText("Beta")).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByTestId("session-launch-btn")).not.toBeDisabled(),
    );

    await act(async () => {
      rejectA?.(new Error("late A failure"));
    });
    await waitFor(() =>
      expect(screen.queryByTestId("session-start-error")).toBeNull(),
    );
    expect(screen.getByTestId("session-launch-btn")).not.toBeDisabled();
  });

  it("shows A's own action state again when navigating back to A", async () => {
    const { client, setDesiredState } = makeStub();
    setDesiredState.mockImplementation(async (id: string) => {
      if (id === "pA") throw new Error("launch failed A");
      return { ...runtime(id), observed_state: "running" };
    });
    renderPage(client);

    fireEvent.click(await screen.findByTestId("session-launch-btn"));
    expect(await screen.findByTestId("session-start-error")).toHaveTextContent(
      "launch failed A",
    );

    act(() => navigateFn("/session/pB"));
    expect(await screen.findByText("Beta")).toBeTruthy();
    await waitFor(() =>
      expect(screen.queryByTestId("session-start-error")).toBeNull(),
    );

    act(() => navigateFn("/session/pA"));
    expect(await screen.findByText("Alpha")).toBeTruthy();
    // Back on A, the view presents A's own state again — not B's, not a
    // leftover from the detour.
    expect(await screen.findByTestId("session-start-error")).toHaveTextContent(
      "launch failed A",
    );
  });
});
