import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider, en } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ToastProvider } from "../../shared/ui";
import { type ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import type {
  ProfileResponse,
  ProfileRuntimeResponse,
} from "../../shared/api/types";
import { SessionEntryPage } from "./SessionEntryPage";
import { SESS_ENTRY_LINK, SESS_ENTRY_LIST, SESS_ENTRY_PAGE } from "./session_keys";

beforeAll(() => {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => undefined;
  }
  if (!HTMLElement.prototype.hasPointerCapture) {
    HTMLElement.prototype.hasPointerCapture = () => false;
  }
  if (!HTMLElement.prototype.releasePointerCapture) {
    HTMLElement.prototype.releasePointerCapture = () => undefined;
  }
  if (!window.DOMRect) {
    vi.stubGlobal(
      "DOMRect",
      class {
        constructor(
          public x = 0,
          public y = 0,
          public width = 0,
          public height = 0,
        ) {}
        top = 0;
        left = 0;
        right = 0;
        bottom = 0;
        toJSON() {
          return {};
        }
      },
    );
  }
});

function profile(overrides: Partial<ProfileResponse> = {}): ProfileResponse {
  return {
    id: "p1",
    name: "Alpha",
    display_number: 1,
    fingerprint_seed: 101,
    group_id: null,
    proxy_id: null,
    timezone: null,
    locale: null,
    screen_width: 1920,
    screen_height: 1080,
    gpu_family: "auto",
    humanize: false,
    human_preset: "default",
    geoip: true,
    clipboard_sync: true,
    auto_launch: false,
    color_scheme: null,
    fingerprint_platform: "windows",
    font_set_id: null,
    launch_args: [],
    extension_paths: [],
    allow_3p_cookies: true,
    set_google_default: true,
    capture_preview: true,
    restore_session: true,
    transparent_proxy: false,
    portable_cookies: false,
    notes: null,
    user_data_dir: "/data/p1",
    sort_order: 0,
    current_config_version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function runtime(
  profileId: string,
  observed: ProfileRuntimeResponse["observed_state"],
  overrides: Partial<ProfileRuntimeResponse> = {},
): ProfileRuntimeResponse {
  return {
    profile_id: profileId,
    display_number: 1,
    desired_state:
      observed === "running" || observed === "starting" ? "running" : "stopped",
    observed_state: observed,
    runtime_instance_id: "inst-1",
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    last_exit_event_id: null,
    last_started_at: observed === "running" ? "2026-01-01T10:00:00Z" : null,
    last_stopped_at: observed === "stopped" ? "2026-01-01T09:00:00Z" : null,
    last_coordinator_error: null,
    updated_at: "2026-01-01T10:00:00Z",
    ...overrides,
  };
}

function makeStub(
  profiles: ProfileResponse[],
  runtimes: Record<string, ProfileRuntimeResponse>,
): ApiClient {
  const summary = {
    entries: Object.values(runtimes).map((entry) => ({
      profile_id: entry.profile_id,
      desired_state: entry.desired_state,
      observed_state: entry.observed_state,
      config_version: entry.config_version,
      runtime_instance_id: entry.runtime_instance_id,
      failure_count: entry.failure_count,
      restart_blocked: entry.restart_blocked,
      last_started_at: entry.last_started_at ?? null,
      last_stopped_at: entry.last_stopped_at ?? null,
      preview_captured_at: null,
      last_coordinator_error: entry.last_coordinator_error ?? null,
      updated_at: entry.updated_at,
    })),
    running_count: Object.values(runtimes).filter(
      (entry) => entry.observed_state === "running",
    ).length,
  };
  return {
    profiles: {
      list: vi.fn(async () => profiles),
      // t076 review f006: the page reads the bounded collection page
      // (server-filtered to running) instead of the whole table; the
      // stub emulates the server status bucket and server paging.
      // t076 review f008: status="running_exact" matches only
      // observed running, and pages are offset server-side.
      listCollection: vi.fn(async (params: Record<string, unknown>) => {
        const bucket = (observed: string) =>
          observed === "error"
            ? "error"
            : observed === "running" || observed === "starting"
              ? "running"
              : "stopped";
        const observedOf = (item: ProfileResponse) =>
          (runtimes[item.id] ?? runtime(item.id, "stopped")).observed_state;
        const items =
          params.status === "running_exact"
            ? profiles.filter((item) => observedOf(item) === "running")
            : params.status === "running"
              ? profiles.filter(
                  (item) => bucket(observedOf(item)) === "running",
                )
              : profiles;
        const page = (params.page as number | undefined) ?? 1;
        const pageSize = (params.page_size as number | undefined) ?? 100;
        return {
          items: items.slice((page - 1) * pageSize, page * pageSize),
          total: items.length,
          page,
          page_size: pageSize,
        };
      }),
      // t076 AC-002: the page reads the batched summary, never the
      // per-profile endpoint; keep the stub for other consumers.
      getRuntime: vi.fn(
        async (id: string) => runtimes[id] ?? runtime(id, "stopped"),
      ),
      getRuntimeSummary: vi.fn(async () => summary),
    },
  } as unknown as ApiClient;
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
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={client}>
              <MemoryRouter>
                <SessionEntryPage />
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
});

describe("SessionEntryPage", () => {
  it("lists only running environments as real session links with status", async () => {
    const profiles = [
      profile({ id: "p1", name: "Alpha" }),
      profile({ id: "p2", name: "Beta" }),
      profile({ id: "p3", name: "Gamma" }),
    ];
    const runtimes = {
      p1: runtime("p1", "running"),
      p2: runtime("p2", "stopped"),
      p3: runtime("p3", "error"),
    };
    renderPage(makeStub(profiles, runtimes));

    const links = await screen.findAllByTestId(SESS_ENTRY_LINK);
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/session/p1");
    expect(links[0]!.textContent).toContain("Alpha");
    expect(links[0]!.textContent).toContain(en.statusRunning);
    expect(screen.getByTestId(SESS_ENTRY_PAGE)).toBeInTheDocument();
    expect(screen.getByTestId(SESS_ENTRY_LIST)).toBeInTheDocument();
    expect(screen.queryByText("Beta")).toBeNull();
    expect(screen.queryByText("Gamma")).toBeNull();
  });

  it("shows the empty state when no environment is running", async () => {
    renderPage(
      makeStub(
        [profile({ id: "p1", name: "Alpha" })],
        { p1: runtime("p1", "stopped") },
      ),
    );

    await screen.findByText(en.sessEntryEmpty);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByTestId("empty-state").textContent).toContain(
      en.sessEntryHint,
    );
    expect(screen.queryAllByTestId(SESS_ENTRY_LINK)).toHaveLength(0);
  });

  // t076 review f008: 105 truly-running environments plus 10
  // starting ones fill the running bucket (115 rows) past one 100-row
  // page. A page-1-only read of the bucket would show 90 running
  // rows (the first 100 bucket rows hold 90 running + 10 starting);
  // an exact-status read of page 1 only would show 100. All 105
  // running rows must appear, and no starting row may.
  it("lists every running environment when the running bucket exceeds one page", async () => {
    const profiles: ProfileResponse[] = [];
    const runtimes: Record<string, ProfileRuntimeResponse> = {};
    for (let i = 0; i < 90; i++) {
      const id = `p-run-${String(i).padStart(3, "0")}`;
      profiles.push(profile({ id, name: `run-${i}` }));
      runtimes[id] = runtime(id, "running");
    }
    for (let i = 0; i < 10; i++) {
      const id = `p-start-${String(i).padStart(3, "0")}`;
      profiles.push(profile({ id, name: `start-${i}` }));
      runtimes[id] = runtime(id, "starting");
    }
    for (let i = 90; i < 105; i++) {
      const id = `p-run-${String(i).padStart(3, "0")}`;
      profiles.push(profile({ id, name: `run-${i}` }));
      runtimes[id] = runtime(id, "running");
    }
    const client = makeStub(profiles, runtimes);
    renderPage(client);

    const links = await screen.findAllByTestId(SESS_ENTRY_LINK);
    expect(links).toHaveLength(105);
    expect(
      links.some(
        (link) => link.getAttribute("href") === "/session/p-run-104",
      ),
    ).toBe(true);
    expect(screen.queryByText("start-0")).toBeNull();
    const calls = vi.mocked(client.profiles.listCollection).mock.calls;
    expect(calls.length).toBe(2);
    expect(
      calls.every(
        (call) =>
          (call[0] as Record<string, unknown>).status === "running_exact",
      ),
    ).toBe(true);
    expect(
      calls.some(
        (call) => (call[0] as Record<string, unknown>).page === 2,
      ),
    ).toBe(true);
  });

  // t076 review test f011: exactly one 100-row page of running
  // environments — `page * page_size >= total` already holds on the
  // first page, so the walk must stop after exactly 1 request (a
  // `>`-instead-of-`>=` termination bug would fetch a second, empty
  // page). All 100 rows must appear.
  it("lists every running environment when the total is exactly one page", async () => {
    const profiles: ProfileResponse[] = [];
    const runtimes: Record<string, ProfileRuntimeResponse> = {};
    for (let i = 0; i < 100; i++) {
      const id = `p-run-${String(i).padStart(3, "0")}`;
      profiles.push(profile({ id, name: `run-${i}` }));
      runtimes[id] = runtime(id, "running");
    }
    const client = makeStub(profiles, runtimes);
    renderPage(client);

    const links = await screen.findAllByTestId(SESS_ENTRY_LINK);
    expect(links).toHaveLength(100);
    expect(
      links.some(
        (link) => link.getAttribute("href") === "/session/p-run-099",
      ),
    ).toBe(true);
    const calls = vi.mocked(client.profiles.listCollection).mock.calls;
    expect(calls.length).toBe(1);
    expect(
      calls.every(
        (call) =>
          (call[0] as Record<string, unknown>).status === "running_exact",
      ),
    ).toBe(true);
  });
});
