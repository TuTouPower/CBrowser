import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "../../i18n";
import type { ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import type { ProfileResponse, ProfileRuntimeResponse } from "../../shared/api/types";
import { ProfileDetailPage } from "./ProfileDetailPage";
import { useProfileEventsSync } from "./useProfilesQuery";
import type { ProfileEventsClient, ProfileRuntimeEvent } from "../../shared/api/sse";

type SseListener = (event: ProfileRuntimeEvent) => void;

function makeFakeSse() {
  let listener: SseListener | null = null;
  const client = {
    onEvent: (l: SseListener) => {
      listener = l;
      return () => {
        listener = null;
      };
    },
    start: () => {},
    stop: () => {},
  };
  return {
    client: client as unknown as ProfileEventsClient,
    emit: (event: ProfileRuntimeEvent) => listener?.(event),
  };
}

function SyncMount({ sse }: { sse: ReturnType<typeof makeFakeSse> }) {
  useProfileEventsSync(sse.client);
  return null;
}

const PROFILE = {
  id: "p1",
  name: "Original",
  proxy: "",
  screen_width: 1920,
  screen_height: 1080,
  tags: [],
  current_config_version: 1,
} as unknown as ProfileResponse;

function runtimeWithControl(control: Record<string, unknown> | null) {
  return {
    profile_id: "p1",
    desired_state: "running",
    observed_state: "running",
    runtime_instance_id: "inst_1",
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    last_exit_event_id: null,
    updated_at: "2026-11-04T00:00:00Z",
    control,
  } as unknown as ProfileRuntimeResponse;
}

function makeStub(control: Record<string, unknown> | null) {
  const runtime = runtimeWithControl(control);
  const restored = {
    profile_id: "p1",
    owner: "agent",
    generation: 5,
    agent_instance_id: "tok_1",
    agent_session_id: "exec-1",
    handoff_reason: null,
    handoff_detail: null,
    agent_reclaim_allowed: true,
    pending_supervisor_close: false,
    updated_at: "2026-11-04T00:00:00Z",
  };
  // Stateful stub: after a restore, the runtime endpoint serves the
  // restored control state, so the mutation's invalidate+refetch
  // converges to agent control (as the real server would).
  let currentRuntime = runtime;
  const restoreControl = vi.fn(async () => {
    currentRuntime = runtimeWithControl(restored);
    return restored;
  });
  const client = {
    profiles: {
      get: vi.fn(async () => PROFILE),
      getRuntime: vi.fn(async () => currentRuntime),
      update: vi.fn(async () => PROFILE),
      delete: vi.fn(async () => undefined),
      duplicate: vi.fn(async () => PROFILE),
      reset: vi.fn(async () => PROFILE),
      retrySearchDefaults: vi.fn(async () => runtime),
      restoreControl,
    },
    // Test-only handle: advance the server truth before emitting an
    // SSE event (SSE is broadcast after the state commit, so a refetch
    // triggered by the event must serve the new state).
    setRuntime: (next: Record<string, unknown> | null) => {
      currentRuntime = runtimeWithControl(next);
    },
  } as unknown as ApiClient & {
    profiles: { restoreControl: ReturnType<typeof vi.fn> };
    setRuntime: (next: Record<string, unknown> | null) => void;
  };
  return client;
}

let stub: ReturnType<typeof makeStub>;

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ApiClientContext.Provider value={stub}>
          <MemoryRouter initialEntries={["/profiles/p1"]}>
            <Routes>
              <Route path="/profiles/:profileId" element={<ProfileDetailPage />} />
            </Routes>
          </MemoryRouter>
        </ApiClientContext.Provider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

function renderPageWithSync(sse: ReturnType<typeof makeFakeSse>) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ApiClientContext.Provider value={stub}>
          <SyncMount sse={sse} />
          <MemoryRouter initialEntries={["/profiles/p1"]}>
            <Routes>
              <Route path="/profiles/:profileId" element={<ProfileDetailPage />} />
            </Routes>
          </MemoryRouter>
        </ApiClientContext.Provider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

const takenOverControl = {
  profile_id: "p1",
  owner: "user",
  generation: 4,
  agent_instance_id: "tok_1",
  agent_session_id: "exec-1",
  handoff_reason: "human_input",
  handoff_detail: null,
  agent_reclaim_allowed: false,
  pending_supervisor_close: false,
  updated_at: "2026-11-04T00:00:00Z",
};

describe("ProfileDetailPage control (t031)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows the control owner, handoff reason, and restore entry after a takeover", async () => {
    stub = makeStub(takenOverControl);
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("profile-control-panel")).toBeTruthy(),
    );
    expect(screen.getByTestId("profile-control-owner").textContent).toBe("Human");
    expect(screen.getByTestId("profile-control-panel").textContent).toContain(
      "human_input",
    );
    expect(
      screen.getByTestId("profile-control-restore-button"),
    ).toBeTruthy();
  });

  it("restore calls the control endpoint and hides the restore entry", async () => {
    stub = makeStub(takenOverControl);
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("profile-control-restore-button")).toBeTruthy(),
    );
    fireEvent.click(screen.getByTestId("profile-control-restore-button"));
    await waitFor(() =>
      expect(stub.profiles.restoreControl).toHaveBeenCalledWith(
        "p1",
        expect.any(String),
      ),
    );
    // The mutation merges owner=agent into the cached runtime, so the
    // restore entry (user-only) disappears.
    await waitFor(() =>
      expect(
        screen.queryByTestId("profile-control-restore-button"),
      ).toBeNull(),
    );
  });

  it("hides the control panel when the runtime carries no control state", async () => {
    stub = makeStub(null);
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("profile-detail-page")).toBeTruthy(),
    );
    expect(screen.queryByTestId("profile-control-panel")).toBeNull();
  });

  it("SSE takeover event refreshes the panel owner (f007 assembly)", async () => {
    stub = makeStub(takenOverControl);
    const sse = makeFakeSse();
    renderPageWithSync(sse);
    await waitFor(() =>
      expect(screen.getByTestId("profile-control-owner").textContent).toBe(
        "Human",
      ),
    );
    const agentControl = {
      profile_id: "p1",
      owner: "agent",
      generation: 5,
      agent_instance_id: "tok_1",
      agent_session_id: "exec-1",
      handoff_reason: null,
      handoff_detail: null,
      agent_reclaim_allowed: true,
      pending_supervisor_close: false,
      updated_at: "2026-11-04T00:00:01Z",
    };
    // Server truth advances before the broadcast (SSE follows the
    // commit), so the event-triggered refetch serves the new state.
    stub.setRuntime(agentControl);
    sse.emit({
      profile_id: "p1",
      control: agentControl,
      updated_at: "2026-11-04T00:00:01Z",
    } as unknown as ProfileRuntimeEvent);
    await waitFor(() =>
      expect(screen.getByTestId("profile-control-owner").textContent).toBe(
        "Agent",
      ),
    );
  });
});
