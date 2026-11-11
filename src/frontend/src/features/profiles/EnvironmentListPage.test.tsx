import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider, en } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ToastProvider } from "../../shared/ui";
import { ApiError, type ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import type {
  GroupResponse,
  ProfileResponse,
  ProfileRuntimeResponse,
  ProxyResponse,
} from "../../shared/api/types";
import { profileKeys } from "./useProfilesQuery";
import { EnvironmentListPage } from "./EnvironmentListPage";

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
    last_started_at:
      observed === "running" ? "2026-01-01T10:00:00Z" : null,
    last_stopped_at:
      observed === "stopped" ? "2026-01-01T09:00:00Z" : null,
    last_coordinator_error: null,
    updated_at: "2026-01-01T10:00:00Z",
    ...overrides,
  };
}

function group(overrides: Partial<GroupResponse> = {}): GroupResponse {
  return {
    id: "g1",
    name: "Work",
    color: "blue",
    sort_order: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function proxy(overrides: Partial<ProxyResponse> = {}): ProxyResponse {
  const { proxy_url, observation_status, ...rest } = overrides;
  return {
    id: "px1",
    name: "US Proxy",
    scheme: "socks5",
    host: "1.2.3.4",
    port: 1080,
    username: null,
    has_password: false,
    credential_revision: 1,
    proxy_url: proxy_url ?? "socks5://1.2.3.4:1080",
    country_code: "US",
    observation_status: observation_status ?? "ok",
    region_label: "California",
    notes: null,
    used_by_count: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...rest,
  };
}

type LooseMock = ReturnType<typeof vi.fn>;

function mockFn(impl: (...args: any[]) => unknown): LooseMock {
  return vi.fn(impl) as unknown as LooseMock;
}

interface StubOptions {
  profiles?: ProfileResponse[];
  groups?: GroupResponse[];
  proxies?: ProxyResponse[];
  runtimes?: Record<string, ProfileRuntimeResponse>;
  deleteImpl?: (id: string) => Promise<void>;
  updateImpl?: (id: string) => Promise<ProfileResponse>;
  setDesiredStateImpl?: (id: string) => Promise<ProfileRuntimeResponse>;
  stopImpl?: (id: string) => Promise<ProfileRuntimeResponse>;
}

function makeStub(options: StubOptions = {}) {
  const profiles = options.profiles ?? [profile()];
  const groups = options.groups ?? [];
  const proxies = options.proxies ?? [];
  const runtimes =
    options.runtimes ??
    Object.fromEntries(
      profiles.map((item) => [item.id, runtime(item.id, "running")]),
    );
  const spies = {
    profiles: {
      list: mockFn(async () => profiles),
      get: mockFn(
        async (id: string) =>
          profiles.find((item) => item.id === id) ?? profiles[0]!,
      ),
      getRuntime: mockFn(
        async (id: string) => runtimes[id] ?? runtime(id, "stopped"),
      ),
      create: mockFn(async () => profiles[0]!),
      update: mockFn(
        options.updateImpl ??
          (async (id: string) =>
            profiles.find((item) => item.id === id) ?? profiles[0]!),
      ),
      delete: mockFn(options.deleteImpl ?? (async () => undefined)),
      duplicate: mockFn(
        async (id: string) =>
          profiles.find((item) => item.id === id) ?? profiles[0]!,
      ),
      reset: mockFn(async () => profiles[0]!),
      setDesiredState: mockFn(
        options.setDesiredStateImpl ??
          (async (id: string, state: "running" | "stopped") =>
            runtime(id, state === "running" ? "running" : "stopped")),
      ),
      stop: mockFn(
        options.stopImpl ?? (async (id: string) => runtime(id, "stopped")),
      ),
      retrySearchDefaults: mockFn(async () => runtime("p1", "running")),
      restoreControl: mockFn(() => undefined),
    },
    groups: {
      list: mockFn(async () => groups),
      create: mockFn(() => undefined),
      update: mockFn(() => undefined),
      remove: mockFn(() => undefined),
      reorder: mockFn(() => undefined),
    },
    proxies: {
      list: mockFn(async () => proxies),
      get: mockFn(() => undefined),
    },
    fontSets: { list: mockFn(async () => []) },
    artifacts: { list: mockFn(async () => []) },
    automation: { status: mockFn(() => undefined) },
    auth: { session: mockFn(() => undefined) },
  };
  return {
    client: spies as unknown as ApiClient,
    spies,
    runtimes,
    profiles,
    groups,
    proxies,
  };
}

function LocationProbe() {
  const { search } = useLocation();
  return <div data-testid="location-search">{search}</div>;
}

let stub: ReturnType<typeof makeStub>;

function renderPage(initialEntries: string[] = ["/"]) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={stub.client}>
              <MemoryRouter initialEntries={initialEntries}>
                <LocationProbe />
                <EnvironmentListPage />
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
  return { ...view, queryClient };
}

function fixture() {
  const profiles = [
    profile({
      id: "p1",
      name: "Alpha",
      group_id: "g1",
      proxy_id: "px1",
      notes: "primary",
      sort_order: 2,
      created_at: "2026-01-03T00:00:00Z",
    }),
    profile({
      id: "p2",
      name: "Beta",
      display_number: 2,
      group_id: null,
      proxy_id: null,
      geoip: false,
      sort_order: 0,
      created_at: "2026-01-01T00:00:00Z",
    }),
    profile({
      id: "p3",
      name: "Gamma",
      group_id: "g2",
      proxy_id: "px2",
      sort_order: 1,
      created_at: "2026-01-02T00:00:00Z",
    }),
  ];
  const groups = [group(), group({ id: "g2", name: "Personal", color: "green" })];
  const proxies = [
    proxy(),
    proxy({ id: "px2", name: "EU Proxy", scheme: "http", country_code: "DE" }),
  ];
  const runtimes = {
    p1: runtime("p1", "running", { last_started_at: "2026-01-01T10:00:00Z" }),
    p2: runtime("p2", "stopped", { last_stopped_at: "2026-01-01T09:00:00Z" }),
    p3: runtime("p3", "error", {
      last_coordinator_error: "coordinator down",
      last_stopped_at: "2026-01-01T08:00:00Z",
    }),
  };
  return { profiles, groups, proxies, runtimes };
}

function rowIds(): string[] {
  return Array.from(document.querySelectorAll('[data-testid^="env-row-"]'))
    .map((node) => node.getAttribute("data-testid") ?? "")
    .filter((id) => id.length > 0);
}

function selectRow(id: string) {
  const wrapper = screen.getByTestId(`env-select-${id}`);
  fireEvent.click(within(wrapper).getByRole("checkbox"));
}

function checkedState(id: string): string | null {
  const wrapper = screen.getByTestId(`env-select-${id}`);
  return within(wrapper).getByRole("checkbox").getAttribute("aria-checked");
}

beforeEach(() => {
  localStorage.clear();
  stub = makeStub(fixture());
});

describe("EnvironmentListPage AC-001 列展示", () => {
  it("renders eight columns with name, notes, group, network and fingerprint", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    const heads = document.querySelectorAll("thead th");
    expect(heads).toHaveLength(8);
    expect(screen.getByText(en.envColName)).toBeInTheDocument();
    expect(screen.getByText(en.envColGroup)).toBeInTheDocument();
    expect(screen.getByText(en.envColNetwork)).toBeInTheDocument();
    expect(screen.getByText(en.envColFingerprint)).toBeInTheDocument();
    expect(screen.getByText(en.envColStatus)).toBeInTheDocument();
    expect(screen.getByText(en.envColLastActive)).toBeInTheDocument();
    expect(screen.getByText(en.envColActions)).toBeInTheDocument();

    const p1 = screen.getByTestId("env-row-p1");
    expect(screen.getByTestId("env-number-p1").textContent).toBe("#0001");
    expect(p1.textContent).toContain("Alpha");
    expect(p1.textContent).toContain("primary");
    expect(p1.textContent).toContain("Work");
    expect(p1.textContent).toContain("US Proxy");
    expect(p1.textContent).toContain("socks5");
    expect(p1.textContent).toContain("US");
    expect(p1.textContent).toContain("windows");

    const p2 = screen.getByTestId("env-row-p2");
    expect(screen.getByTestId("env-number-p2").textContent).toBe("#0002");
    expect(p2.textContent).toContain(en.envUngrouped);
    expect(p2.textContent).not.toContain(en.envGeoipFollowProxy);
  });

  it("shows a direct-connection warning and the geoip follow-proxy hint", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    const direct = screen.getByTestId("env-direct-p2");
    expect(direct.textContent).toContain(en.envDirect);
    expect(direct.textContent).toContain(en.envDirectWarning);
    expect(direct.querySelector("svg")).toBeTruthy();
    expect(screen.queryByTestId("env-direct-p1")).toBeNull();

    const p1 = screen.getByTestId("env-row-p1");
    expect(p1.textContent).toContain(en.envGeoipFollowProxy);
  });

  it("renders all five status tones with text and an error reason tooltip", async () => {
    const profiles = [
      profile({ id: "s1", name: "Starting" }),
      profile({ id: "s2", name: "Stopping" }),
      profile({ id: "s3", name: "Running" }),
      profile({ id: "s4", name: "Error" }),
      profile({ id: "s5", name: "Stopped" }),
    ];
    const runtimes: Record<string, ProfileRuntimeResponse> = {
      s1: runtime("s1", "starting"),
      s2: runtime("s2", "stopping"),
      s3: runtime("s3", "running"),
      s4: runtime("s4", "error", {
        last_coordinator_error: "coordinator down",
      }),
      s5: runtime("s5", "stopped"),
    };
    stub = makeStub({ profiles, runtimes });
    renderPage();
    await screen.findByTestId("env-table");
    expect(screen.getByTestId("env-status-s1").textContent).toContain(
      en.statusStarting,
    );
    expect(screen.getByTestId("env-status-s2").textContent).toContain(
      en.statusStopping,
    );
    expect(screen.getByTestId("env-status-s3").textContent).toContain(
      en.statusRunning,
    );
    expect(screen.getByTestId("env-status-s4").textContent).toContain(
      en.statusError,
    );
    expect(screen.getByTestId("env-status-s5").textContent).toContain(
      en.statusStopped,
    );
    expect(screen.getByTestId("env-error-tooltip-s4")).toBeInTheDocument();
    expect(screen.getByTestId("env-error-reason-s4").textContent).toContain(
      "coordinator down",
    );
    expect(screen.queryByTestId("env-error-tooltip-s3")).toBeNull();
  });

  it("shows running duration while running and relative stopped time otherwise", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    const runningPrefix = en.envRunningFor.split("{time}")[0]!;
    const stoppedPrefix = en.envLastStopped.split("{time}")[0]!;
    const stoppedSuffix = en.envLastStopped.split("{time}")[1]!;
    expect(screen.getByTestId("env-row-p1").textContent).toContain(
      runningPrefix,
    );
    expect(screen.getByTestId("env-row-p1").textContent).not.toContain(
      stoppedPrefix,
    );
    expect(screen.getByTestId("env-row-p2").textContent).toContain(
      stoppedPrefix,
    );
    expect(screen.getByTestId("env-row-p2").textContent).toContain(
      stoppedSuffix,
    );
  });
});

describe("EnvironmentListPage AC-002 组合筛选与 URL", () => {
  it("restores combined filters from URL query parameters", async () => {
    renderPage(["/?q=Alpha&status=running&group=g1&proxy=px1&sort=name"]);
    await screen.findByTestId("env-table");
    expect(rowIds()).toEqual(["env-row-p1"]);
    expect(screen.getByTestId("location-search").textContent).toContain(
      "q=Alpha",
    );
    expect(screen.getByTestId("location-search").textContent).toContain(
      "status=running",
    );
    expect(screen.getByTestId("location-search").textContent).toContain(
      "group=g1",
    );
    expect(screen.getByTestId("location-search").textContent).toContain(
      "proxy=px1",
    );
    expect(screen.getByTestId("location-search").textContent).toContain(
      "sort=name",
    );
  });

  it("filters by status, ungrouped, proxy and search text independently", async () => {
    renderPage(["/?status=error"]);
    await screen.findByTestId("env-table");
    expect(rowIds()).toEqual(["env-row-p3"]);
  });

  it("filters ungrouped profiles", async () => {
    renderPage(["/?group=ungrouped"]);
    await screen.findByTestId("env-table");
    expect(rowIds()).toEqual(["env-row-p2"]);
  });

  it("filters by proxy id", async () => {
    renderPage(["/?proxy=px2"]);
    await screen.findByTestId("env-table");
    expect(rowIds()).toEqual(["env-row-p3"]);
  });

  it("filters by notes and proxy name in the search field", async () => {
    renderPage(["/?q=EU"]);
    await screen.findByTestId("env-table");
    expect(rowIds()).toEqual(["env-row-p3"]);
  });

  it("writes the search text into the URL query parameters", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    fireEvent.change(screen.getByTestId("env-search"), {
      target: { value: "Beta" },
    });
    await waitFor(() =>
      expect(screen.getByTestId("location-search").textContent).toContain(
        "q=Beta",
      ),
    );
    await waitFor(() => expect(rowIds()).toEqual(["env-row-p2"]));
  });

  it("sorts by name", async () => {
    renderPage(["/?sort=name"]);
    await screen.findByTestId("env-table");
    expect(rowIds()).toEqual([
      "env-row-p1",
      "env-row-p2",
      "env-row-p3",
    ]);
  });

  it("sorts by manual order", async () => {
    renderPage(["/?sort=manual"]);
    await screen.findByTestId("env-table");
    expect(rowIds()).toEqual([
      "env-row-p2",
      "env-row-p3",
      "env-row-p1",
    ]);
  });

  it("offers clear filters when no rows match", async () => {
    renderPage(["/?q=does-not-exist"]);
    const empty = await screen.findByTestId("env-empty-state");
    expect(empty.textContent).toContain(en.envNoResults);
    fireEvent.click(screen.getByTestId("env-clear-filters-empty"));
    await waitFor(() =>
      expect(screen.getByTestId("location-search").textContent).toBe(""),
    );
    await waitFor(() =>
      expect(rowIds()).toEqual([
        "env-row-p2",
        "env-row-p3",
        "env-row-p1",
      ]),
    );
  });

  it("shows the create-first empty state when no environments exist", async () => {
    stub = makeStub({ profiles: [], groups: [], proxies: [] });
    renderPage();
    const empty = await screen.findByTestId("env-empty-state");
    expect(empty.textContent).toContain(en.envEmptyTitle);
    expect(screen.getByTestId("env-empty-create")).toBeInTheDocument();
  });
});

describe("EnvironmentListPage AC-003 布局与卡片", () => {
  it("persists the card layout across a refresh and shows a preview placeholder", async () => {
    const first = renderPage();
    await screen.findByTestId("env-table");
    fireEvent.click(screen.getByTestId("env-layout-card"));
    await screen.findByTestId("env-card-grid");
    expect(localStorage.getItem("cbrowser.environments.layout")).toBe("card");
    first.unmount();

    renderPage();
    const grid = await screen.findByTestId("env-card-grid");
    expect(screen.queryByTestId("env-table")).toBeNull();
    const card = screen.getByTestId("env-card-p1");
    expect(card.textContent).toContain("Alpha");
    expect(card.textContent).toContain("Work");
    expect(card.textContent).toContain("US Proxy");
    expect(card.textContent).toContain("windows");
    const placeholder = screen.getByTestId("env-card-preview-p1");
    expect(placeholder.textContent).toBe("");
    expect(grid).toBeInTheDocument();
  });

  it("switches back to the list layout", async () => {
    localStorage.setItem("cbrowser.environments.layout", "card");
    renderPage();
    await screen.findByTestId("env-card-grid");
    fireEvent.click(screen.getByTestId("env-layout-list"));
    await screen.findByTestId("env-table");
    expect(localStorage.getItem("cbrowser.environments.layout")).toBe("list");
  });
});

describe("EnvironmentListPage AC-004 SSE 增量", () => {
  it("refreshes row status and running count from a runtime cache update", async () => {
    const { queryClient } = renderPage();
    await screen.findByTestId("env-table");
    expect(screen.getByTestId("env-status-p1").textContent).toContain(
      en.statusRunning,
    );
    expect(screen.getByTestId("env-running-count").textContent).toContain("1");

    const next = runtime("p1", "error", {
      last_coordinator_error: "sse failure",
    });
    stub.runtimes.p1 = next;
    act(() => {
      queryClient.setQueryData(profileKeys.runtime("p1"), next);
    });

    await waitFor(() =>
      expect(screen.getByTestId("env-status-p1").textContent).toContain(
        en.statusError,
      ),
    );
    expect(screen.getByTestId("env-status-p1").textContent).not.toContain(
      en.statusRunning,
    );
    await waitFor(() =>
      expect(screen.getByTestId("env-running-count").textContent).toContain(
        "0",
      ),
    );
  });
});

describe("EnvironmentListPage AC-005 批量操作", () => {
  it("starts each selected item with its own idempotency key", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    selectRow("p1");
    selectRow("p2");
    await screen.findByTestId("env-batch-bar");
    fireEvent.click(screen.getByTestId("env-batch-start"));
    await waitFor(() =>
      expect(stub.spies.profiles.setDesiredState).toHaveBeenCalledTimes(2),
    );
    const calls = stub.spies.profiles.setDesiredState.mock.calls;
    const keys = calls.map((call) => call[2]);
    expect(keys.every((key) => typeof key === "string" && key.length > 0)).toBe(
      true,
    );
    expect(new Set(keys).size).toBe(2);
    expect(calls.map((call) => call[1])).toEqual(["running", "running"]);
  });

  it("stops each selected item with its own idempotency key", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    selectRow("p1");
    selectRow("p3");
    await screen.findByTestId("env-batch-bar");
    fireEvent.click(screen.getByTestId("env-batch-stop"));
    await waitFor(() =>
      expect(stub.spies.profiles.stop).toHaveBeenCalledTimes(2),
    );
    const keys = stub.spies.profiles.stop.mock.calls.map((call) => call[1]);
    expect(keys.every((key) => typeof key === "string" && key.length > 0)).toBe(
      true,
    );
    expect(new Set(keys).size).toBe(2);
  });

  it("moves each selected item to a group with its own idempotency key", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    selectRow("p1");
    selectRow("p2");
    await screen.findByTestId("env-batch-bar");
    fireEvent.click(screen.getByTestId("env-batch-move"));
    fireEvent.click(screen.getByTestId("env-move-group-g2"));
    await waitFor(() =>
      expect(stub.spies.profiles.update).toHaveBeenCalledTimes(2),
    );
    const calls = stub.spies.profiles.update.mock.calls;
    expect(
      calls.every((call) => (call[1] as { group_id?: string }).group_id === "g2"),
    ).toBe(true);
    const keys = calls.map((call) => call[2]);
    expect(keys.every((key) => typeof key === "string" && key.length > 0)).toBe(
      true,
    );
    expect(new Set(keys).size).toBe(2);
  });

  it("deletes each selected item with its own idempotency key", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    selectRow("p1");
    selectRow("p2");
    await screen.findByTestId("env-batch-bar");
    // P2: 批量删除需二次确认。
    fireEvent.click(screen.getByTestId("env-batch-delete"));
    fireEvent.click(await screen.findByTestId("env-batch-delete-accept"));
    await waitFor(() =>
      expect(stub.spies.profiles.delete).toHaveBeenCalledTimes(2),
    );
    const keys = stub.spies.profiles.delete.mock.calls.map((call) => call[1]);
    expect(keys.every((key) => typeof key === "string" && key.length > 0)).toBe(
      true,
    );
    expect(new Set(keys).size).toBe(2);
  });

  it("keeps failed items selected and reports the success/failure summary", async () => {
    stub = makeStub({
      ...fixture(),
      deleteImpl: async (id: string) => {
        if (id === "p2") {
          throw new ApiError("running", 409, undefined, "profile_running");
        }
        return undefined;
      },
    });
    renderPage();
    await screen.findByTestId("env-table");
    selectRow("p1");
    selectRow("p2");
    await screen.findByTestId("env-batch-bar");
    fireEvent.click(screen.getByTestId("env-batch-delete"));
    fireEvent.click(await screen.findByTestId("env-batch-delete-accept"));

    await waitFor(() =>
      expect(screen.getByTestId("toast-item").textContent).toContain(
        en.envBatchResult
          .replace("{success}", "1")
          .replace("{failed}", "1"),
      ),
    );
    await waitFor(() => expect(checkedState("p1")).toBe("false"));
    expect(checkedState("p2")).toBe("true");
    expect(screen.getByTestId("env-batch-bar").textContent).toContain("1");
  });
});
