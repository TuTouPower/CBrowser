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
import { type ApiClient } from "../../shared/api/client";
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
    include_cjk_fonts: false,
    humanize: false,
    human_preset: "default",
    geoip: true,
    clipboard_sync: true,
    auto_launch: false,
    color_scheme: "light",
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
  /** t078: profile id -> stage at which its deletion operation fails. */
  deletionFailAt?: Record<string, string>;
  updateImpl?: (id: string) => Promise<ProfileResponse>;
  setDesiredStateImpl?: (id: string) => Promise<ProfileRuntimeResponse>;
  stopImpl?: (id: string) => Promise<ProfileRuntimeResponse>;
}

function makeStub(options: StubOptions = {}) {
  const groups = options.groups ?? [];
  const proxies = options.proxies ?? [];
  // t076 review f006: the server fills the row display names into the
  // collection page — the stub emulates that contract so row assertions
  // exercise the page's name rendering, not a whole-table lookup.
  const profiles = (options.profiles ?? [profile()]).map((item) => {
    const group = groups.find((entry) => entry.id === item.group_id);
    const proxy = proxies.find((entry) => entry.id === item.proxy_id);
    return {
      ...item,
      group_name: group?.name ?? item.group_name ?? null,
      group_color: group?.color ?? item.group_color ?? null,
      proxy_name: proxy?.name ?? item.proxy_name ?? null,
    };
  });
  const runtimes =
    options.runtimes ??
    Object.fromEntries(
      profiles.map((item) => [item.id, runtime(item.id, "running")]),
    );
  const deletionOps = new Map<
    string,
    {
      id: string;
      profile_id: string;
      stage: string;
      failed_stage: string | null;
      error: string | null;
      retry_count: number;
    }
  >();
  const deletionBatches = new Map<string, string[]>();
  const deletionFailureConsumed = new Set<string>();
  let deletionCounter = 0;
  const spies = {
    profiles: {
      list: mockFn(async () => profiles),
      // t076 AC-001: the page reads the bounded server page; the stub
      // emulates the server contract (search/group/proxy/status/
      // platform/sort/paging) so filter tests still exercise the page.
      listCollection: mockFn(async (params: Record<string, unknown>) => {
        let items = [...profiles];
        const search = (params.search as string | undefined)?.toLowerCase();
        if (search) {
          const proxyById = new Map(proxies.map((item) => [item.id, item]));
          items = items.filter((item) =>
            [
              item.name,
              item.notes ?? "",
              proxyById.get(item.proxy_id ?? "")?.name ?? "",
            ].some((value) => value.toLowerCase().includes(search)),
          );
        }
        const groupId = params.group_id as string | undefined;
        if (groupId) {
          items =
            groupId === "ungrouped"
              ? items.filter((item) => item.group_id == null)
              : items.filter((item) => item.group_id === groupId);
        }
        const proxyId = params.proxy_id as string | undefined;
        if (proxyId) {
          items =
            proxyId === "direct"
              ? items.filter((item) => item.proxy_id == null)
              : items.filter((item) => item.proxy_id === proxyId);
        }
        const status = params.status as string | undefined;
        if (status && status !== "all") {
          const bucket = (observed: string) =>
            observed === "error"
              ? "error"
              : observed === "running" || observed === "starting"
                ? "running"
                : "stopped";
          items = items.filter(
            (item) =>
              bucket(
                (runtimes[item.id] ?? runtime(item.id, "stopped"))
                  .observed_state,
              ) === status,
          );
        }
        const platform = params.platform as string | undefined;
        if (platform && platform !== "all") {
          items = items.filter(
            (item) => (item.fingerprint_platform ?? "windows") === platform,
          );
        }
        if (params.sort === "name") {
          items.sort((a, b) => a.name.localeCompare(b.name));
        } else if (params.sort === "created") {
          items.sort(
            (a, b) =>
              Date.parse(b.created_at) - Date.parse(a.created_at),
          );
        } else {
          // Server default (manual): stable sort_order, then created_at.
          items.sort((a, b) => a.sort_order - b.sort_order);
        }
        const page = (params.page as number | undefined) ?? 1;
        const pageSize = (params.page_size as number | undefined) ?? 50;
        const total = items.length;
        return {
          items: items.slice((page - 1) * pageSize, page * pageSize),
          total,
          page,
          page_size: pageSize,
        };
      }),
      get: mockFn(
        async (id: string) =>
          profiles.find((item) => item.id === id) ?? profiles[0]!,
      ),
      getRuntime: mockFn(
        async (id: string) => runtimes[id] ?? runtime(id, "stopped"),
      ),
      getRuntimeSummary: mockFn(async () => ({
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
          preview_captured_at:
            (entry as { preview_captured_at?: string | null })
              .preview_captured_at ?? null,
          last_coordinator_error: entry.last_coordinator_error ?? null,
          updated_at: entry.updated_at,
        })),
        running_count: Object.values(runtimes).filter(
          (entry) => entry.observed_state === "running",
        ).length,
      })),
      create: mockFn(async () => profiles[0]!),
      update: mockFn(
        options.updateImpl ??
          (async (id: string) =>
            profiles.find((item) => item.id === id) ?? profiles[0]!),
      ),
      delete: mockFn(async () => undefined),
      // t078: deletion lifecycle fake — emulates the durable server
      // contract: create returns accepted operations; each batch read
      // advances non-terminal operations to their outcome (done, or
      // failed once at the stage named by deletionFailAt); retry
      // re-queues a failed operation, which then succeeds.
      createDeletions: mockFn(async (ids: string[]) => {
        deletionCounter += 1;
        const batchId = `batch-${deletionCounter}`;
        const operations = ids.map((id) => {
          const op = {
            id: `op-${id}`,
            batch_id: batchId,
            profile_id: id,
            profile_name:
              profiles.find((item) => item.id === id)?.name ?? id,
            stage: "accepted",
            failed_stage: null as string | null,
            error: null as string | null,
            retry_count: 0,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          };
          deletionOps.set(op.id, op);
          return op;
        });
        deletionBatches.set(
          batchId,
          operations.map((op) => op.id),
        );
        // Snapshot copies: the real API returns fresh JSON per read;
        // returning the mutated store objects would defeat React
        // Query's structural sharing in tests.
        return {
          batch_id: batchId,
          operations: operations.map((op) => ({ ...op })),
        };
      }),
      getDeletionBatch: mockFn(async (batchId: string) => {
        const operations = (deletionBatches.get(batchId) ?? []).map(
          (opId) => {
            const op = deletionOps.get(opId)!;
            if (op.stage !== "done" && op.stage !== "failed") {
              const failStage = options.deletionFailAt?.[op.profile_id];
              if (failStage && !deletionFailureConsumed.has(op.id)) {
                deletionFailureConsumed.add(op.id);
                op.stage = "failed";
                op.failed_stage = failStage;
                op.error = "simulated deletion failure";
              } else {
                op.stage = "done";
              }
            }
            return { ...op };
          },
        );
        return { batch_id: batchId, operations };
      }),
      getDeletion: mockFn(
        async (opId: string) => deletionOps.get(opId),
      ),
      retryDeletion: mockFn(async (opId: string) => {
        const op = deletionOps.get(opId)!;
        op.stage = op.failed_stage ?? "accepted";
        op.failed_stage = null;
        op.error = null;
        op.retry_count += 1;
        return op;
      }),
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
    profileBatchJobs: {
      submit: mockFn(async (input: { action: string; profile_ids: string[]; group_id?: string | null }) => ({
        job_id: "job-test",
        state: "running",
        total: input.profile_ids.length,
        completed: 0,
        failed: 0,
      })),
      get: mockFn(async () => ({
        job_id: "job-test",
        state: "running",
        total: 2,
        completed: 0,
        failed: 0,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        members: [],
      })),
    },
    groups: {
      list: mockFn(async () => groups),
      // t076 review f006: filter options and the move menu read the
      // bounded candidate endpoints, never the whole table.
      listCandidates: mockFn(async () =>
        groups.map((item) => ({ id: item.id, name: item.name })),
      ),
      get: mockFn(async (id: string) => {
        const found = groups.find((item) => item.id === id);
        if (!found) throw new Error(`Group ${id} not found`);
        return found;
      }),
      create: mockFn(() => undefined),
      update: mockFn(() => undefined),
      remove: mockFn(() => undefined),
      reorder: mockFn(() => undefined),
    },
    proxies: {
      list: mockFn(async () => proxies),
      listCandidates: mockFn(async () =>
        proxies.map((item) => ({
          id: item.id,
          name: item.name,
          country_code: item.country_code ?? null,
          country_name: null,
          city: null,
        })),
      ),
      get: mockFn(async (id: string) => {
        const found = proxies.find((item) => item.id === id);
        if (!found) throw new Error(`Proxy ${id} not found`);
        return found;
      }),
    },
    fontSets: { list: mockFn(async () => ({ items: [], default_font_set_id: { windows: null, macos: null } })) },
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
      fingerprint_platform: "macos",
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
  // t078 AC-006: 旧用例断言八列含「最后活跃」表头，锁定了已按 p114
  // 移除的相对时间列，故整体替换为七列新语义用例（非就地改预期）。
  it("renders seven columns with name, note tooltip trigger, group, proxy and localized platform without exposing internal IDs", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    const heads = document.querySelectorAll("thead th");
    expect(heads).toHaveLength(7);
    expect(screen.getByText(en.envColName)).toBeInTheDocument();
    expect(screen.getByText(en.envColGroup)).toBeInTheDocument();
    expect(screen.getByText(en.envColNetwork)).toBeInTheDocument();
    expect(screen.getByText(en.envColFingerprint)).toBeInTheDocument();
    expect(screen.getByText(en.envColStatus)).toBeInTheDocument();
    expect(screen.queryByText(en.envColLastActive)).toBeNull();
    expect(screen.getByText(en.envColActions)).toBeInTheDocument();

    const p1 = screen.getByTestId("env-row-p1");
    expect(screen.queryByTestId("env-number-p1")).toBeNull();
    expect(p1.textContent).toContain("Alpha");
    expect(screen.getByTestId("env-note-trigger-p1")).toHaveAttribute(
      "aria-label",
      "primary",
    );
    expect(p1.textContent).toContain("Work");
    expect(p1.textContent).toContain("US Proxy");
    expect(p1.textContent).toContain("Windows");

    const p2 = screen.getByTestId("env-row-p2");
    expect(screen.queryByTestId("env-number-p2")).toBeNull();
    expect(p2.textContent).toContain(en.envUngrouped);
    expect(p2.textContent).toContain("macOS");
    expect(p2.textContent).not.toContain(en.envGeoipFollowProxy);
  });

  // t073 AC-004: 未显式设置时区时不再打印默认/自动匹配时区提示。
  // 旧用例断言 geoip 环境显示 envGeoipFollowProxy，锁定了默认时区噪音，
  // 故整体替换为新语义用例（非就地改预期）。
  it("shows direct proxy label and hides default timezone hint", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    const direct = screen.getByTestId("env-direct-p2");
    expect(direct.textContent).toContain(en.envDirect);
    expect(screen.queryByTestId("env-direct-p1")).toBeNull();

    const p1 = screen.getByTestId("env-row-p1");
    expect(p1.textContent).not.toContain(en.envGeoipFollowProxy);
  });

  it("仅显式设置的自定义时区出现在环境行中（AC-004）", async () => {
    stub = makeStub({
      profiles: [profile({ id: "p1", timezone: "Asia/Shanghai" })],
    });
    renderPage();
    await screen.findByTestId("env-table");
    expect(screen.getByTestId("env-row-p1").textContent).toContain(
      "Asia/Shanghai",
    );
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
    expect(screen.queryByTestId("env-error-tooltip-s3")).toBeNull();
  });

  // t078 AC-006: 旧用例断言表格行显示运行时长/相对停止时间，锁定了
  // 已移除的最后活跃列，故整体替换：表格行不再出现相对时间文案，
  // 卡片布局保留该信息（p114 只点名表格列与页头统计）。
  it("hides relative activity time in table rows but keeps it on cards", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    const runningPrefix = en.envRunningFor.split("{time}")[0]!;
    const stoppedPrefix = en.envLastStopped.split("{time}")[0]!;
    expect(screen.getByTestId("env-row-p1").textContent).not.toContain(
      runningPrefix,
    );
    expect(screen.getByTestId("env-row-p2").textContent).not.toContain(
      stoppedPrefix,
    );

    fireEvent.click(screen.getByTestId("env-layout-card"));
    await screen.findByTestId("env-card-grid");
    expect(screen.getByTestId("env-card-p1").textContent).toContain(
      runningPrefix,
    );
    expect(screen.getByTestId("env-card-p2").textContent).toContain(
      stoppedPrefix,
    );
  });
});

describe("EnvironmentListPage AC-002 组合筛选与 URL", () => {
  it("restores combined filters from URL query parameters", async () => {
    renderPage(["/?q=Alpha&status=running&group=g1&platform=windows&proxy=px1&sort=name"]);
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
      "platform=windows",
    );
    expect(screen.getByTestId("location-search").textContent).toContain(
      "proxy=px1",
    );
    expect(screen.getByTestId("location-search").textContent).toContain(
      "sort=name",
    );
  });

  it("filters by status, ungrouped, platform, proxy and search text independently", async () => {
    renderPage(["/?status=error"]);
    await screen.findByTestId("env-table");
    expect(rowIds()).toEqual(["env-row-p3"]);
  });

  it("filters by platform", async () => {
    renderPage(["/?platform=macos"]);
    await screen.findByTestId("env-table");
    expect(rowIds()).toEqual(["env-row-p2"]);
  });

  it("filters ungrouped profiles", async () => {
    renderPage(["/?group=ungrouped"]);
    await screen.findByTestId("env-table");
    expect(rowIds()).toEqual(["env-row-p2"]);
  });

  it("filters by proxy id and direct proxy", async () => {
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
    expect(card.textContent).toContain("Windows");
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
  // t078 AC-006: 旧用例同时断言页头运行环境计数随缓存更新，该统计块
  // 已按 p114 移除，故整体替换为仅行状态刷新的新语义用例。
  it("refreshes row status from a runtime cache update", async () => {
    const { queryClient } = renderPage();
    await screen.findByTestId("env-table");
    expect(screen.getByTestId("env-status-p1").textContent).toContain(
      en.statusRunning,
    );
    expect(screen.queryByTestId("env-running-count")).toBeNull();

    const next = runtime("p1", "error", {
      last_coordinator_error: "sse failure",
    });
    stub.runtimes.p1 = next;
    // t076 AC-002/AC-003: the list reads runtime state from the batched
    // summary cache (kept in step by the SSE sync); writing the summary
    // is the cache update the page observes.
    const summaryEntries = Object.values(stub.runtimes).map((entry) => ({
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
    }));
    act(() => {
      queryClient.setQueryData(profileKeys.runtimeSummary(), {
        entries: summaryEntries,
        running_count: summaryEntries.filter(
          (entry) => entry.observed_state === "running",
        ).length,
      });
    });

    await waitFor(() =>
      expect(screen.getByTestId("env-status-p1").textContent).toContain(
        en.statusError,
      ),
    );
    expect(screen.getByTestId("env-status-p1").textContent).not.toContain(
      en.statusRunning,
    );
    expect(screen.queryByTestId("env-running-count")).toBeNull();
  });
});

describe("EnvironmentListPage t076 集合分页", () => {
  it("pages server-side and never issues per-profile runtime reads", async () => {
    const many = Array.from({ length: 60 }, (_, index) =>
      profile({
        id: `px-${index}`,
        name: `Env ${index}`,
        display_number: index + 1,
        sort_order: index,
        created_at: "2026-01-01T00:00:00Z",
      }),
    );
    stub = makeStub({ profiles: many });
    renderPage();
    await screen.findByTestId("env-table");
    expect(rowIds()).toHaveLength(50);
    expect(
      screen.getByTestId("env-list-page-status").textContent,
    ).toContain("1");
    expect(
      stub.spies.profiles.listCollection.mock.calls[0]?.[0],
    ).toMatchObject({ page: 1, page_size: 50 });
    // t076 AC-002: runtime state comes from one summary read; the
    // per-profile endpoint is never called for the list.
    expect(stub.spies.profiles.getRuntime).not.toHaveBeenCalled();
    expect(stub.spies.profiles.getRuntimeSummary).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("env-list-next-page"));
    await waitFor(() =>
      expect(rowIds()).toHaveLength(10),
    );
    expect(
      screen.getByTestId("env-list-page-status").textContent,
    ).toContain("2");
    const pages = stub.spies.profiles.listCollection.mock.calls.map(
      (call) => (call[0] as { page: number }).page,
    );
    expect(pages).toContain(2);
    expect(stub.spies.profiles.getRuntime).not.toHaveBeenCalled();
  });
});

describe("EnvironmentListPage AC-007 环境批量作业", () => {
  it("submits one frozen-scope start job for all selected items", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    selectRow("p1");
    selectRow("p2");
    await screen.findByTestId("env-batch-bar");
    fireEvent.click(screen.getByTestId("env-batch-start"));
    await waitFor(() =>
      expect(stub.spies.profileBatchJobs.submit).toHaveBeenCalledTimes(1),
    );
    const input = stub.spies.profileBatchJobs.submit.mock.calls[0]![0];
    expect(input.action).toBe("start");
    expect(new Set(input.profile_ids)).toEqual(new Set(["p1", "p2"]));
  });

  it("submits one frozen-scope stop job for all selected items", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    selectRow("p1");
    selectRow("p3");
    await screen.findByTestId("env-batch-bar");
    fireEvent.click(screen.getByTestId("env-batch-stop"));
    await waitFor(() =>
      expect(stub.spies.profileBatchJobs.submit).toHaveBeenCalledTimes(1),
    );
    const input = stub.spies.profileBatchJobs.submit.mock.calls[0]![0];
    expect(input.action).toBe("stop");
    expect(new Set(input.profile_ids)).toEqual(new Set(["p1", "p3"]));
  });

  it("shows the batch job progress bar after submission", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    selectRow("p1");
    selectRow("p2");
    await screen.findByTestId("env-batch-bar");
    fireEvent.click(screen.getByTestId("env-batch-start"));
    await screen.findByTestId("env-batch-job-status");
    expect(screen.getByTestId("env-batch-job-status").textContent).toContain(
      "0/2",
    );
  });

  it("submits one moveToGroup job carrying the target group", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    selectRow("p1");
    selectRow("p2");
    await screen.findByTestId("env-batch-bar");
    fireEvent.click(screen.getByTestId("env-batch-move"));
    fireEvent.click(screen.getByTestId("env-move-group-g2"));
    await waitFor(() =>
      expect(stub.spies.profileBatchJobs.submit).toHaveBeenCalledTimes(1),
    );
    const input = stub.spies.profileBatchJobs.submit.mock.calls[0]![0];
    expect(input.action).toBe("moveToGroup");
    expect(input.group_id).toBe("g2");
    expect(new Set(input.profile_ids)).toEqual(new Set(["p1", "p2"]));
  });

  // t078 AC-002/AC-005: 旧两条用例锁定「逐个 DELETE + 幂等键 + toast
  // 汇总」的已废止批量删除语义，故整体替换为居中模态 + 持久化批量
  // 删除端点的新语义用例（非就地改预期）。
  it("deletes the confirmed set through one batch request after explicit confirmation", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    selectRow("p1");
    selectRow("p2");
    await screen.findByTestId("env-batch-bar");
    fireEvent.click(screen.getByTestId("env-batch-delete"));

    // 确认前不发删除请求，弹窗内列出冻结的目标名称。
    await screen.findByTestId("env-delete-dialog");
    expect(stub.spies.profiles.createDeletions).not.toHaveBeenCalled();
    expect(screen.getByTestId("env-delete-target-p1")).toBeInTheDocument();
    expect(screen.getByTestId("env-delete-target-p2")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("env-delete-accept"));
    await waitFor(() =>
      expect(stub.spies.profiles.createDeletions).toHaveBeenCalledTimes(1),
    );
    // AC-005 严格集合：请求目标恰为确认的 {p1, p2}，未选中的 p3
    // 不得混入（arrayContaining 无法发现多发，review f001）。
    const requestedIds = stub.spies.profiles.createDeletions.mock
      .calls[0]?.[0] as string[];
    expect(requestedIds).toHaveLength(2);
    expect([...requestedIds].sort()).toEqual(["p1", "p2"]);
    expect(stub.spies.profiles.delete).not.toHaveBeenCalled();

    // 服务端逐项完成后，弹窗显示已删除；关弹窗后选中态已清除
    // （模态打开时背景 aria-hidden，role 查询不可用，故关后断言）。
    await waitFor(
      () =>
        expect(
          screen.getByTestId("env-delete-stage-p1").textContent,
        ).toContain(en.envDeleteStageDone),
      { timeout: 5000 },
    );
    fireEvent.click(screen.getByTestId("env-delete-close"));
    await waitFor(() =>
      expect(screen.queryByTestId("env-delete-dialog")).toBeNull(),
    );
    expect(checkedState("p1")).toBe("false");
    expect(checkedState("p2")).toBe("false");
  });

  // t078 AC-001（review test f002）：删除入口须覆盖全部运行状态与
  // 卡片布局，而非只有表格的 running/stopped 两行。
  it("shows a rightmost danger delete entry in every runtime state and in card layout", async () => {
    const base = fixture();
    const profiles = [
      ...base.profiles,
      profile({ id: "p4", name: "Delta", sort_order: 3 }),
      profile({ id: "p5", name: "Epsilon", sort_order: 4 }),
    ];
    const runtimes = {
      ...base.runtimes,
      p4: runtime("p4", "starting"),
      p5: runtime("p5", "stopping"),
    };
    stub = makeStub({
      profiles,
      groups: base.groups,
      proxies: base.proxies,
      runtimes,
    });
    renderPage();
    await screen.findByTestId("env-table");

    for (const id of ["p1", "p2", "p3", "p4", "p5"]) {
      const del = screen.getByTestId(`env-action-delete-${id}`);
      expect(del.parentElement?.lastElementChild).toBe(del);
    }
    // 运行/启动中：删除 title 说明先停后删，停止入口可用。
    expect(screen.getByTestId("env-action-delete-p1")).toHaveAttribute(
      "title",
      en.envDeleteHintRunning,
    );
    expect(screen.getByTestId("env-action-delete-p4")).toHaveAttribute(
      "title",
      en.envDeleteHintRunning,
    );
    expect(screen.getByTestId("env-action-stop-p4")).not.toBeDisabled();
    // 停止中（过渡态）：启动被禁用并有状态，删除入口仍在。
    expect(screen.getByTestId("env-action-start-p5")).toBeDisabled();
    expect(screen.getByTestId("env-action-delete-p5")).toHaveAttribute(
      "title",
      en.envDelete,
    );
    // 异常态：无停止入口，删除入口仍在。
    expect(screen.queryByTestId("env-action-stop-p3")).toBeNull();
    expect(screen.getByTestId("env-action-delete-p3")).toBeInTheDocument();

    // 卡片布局共用同一操作区，五种状态的删除入口都在。
    fireEvent.click(screen.getByTestId("env-layout-card"));
    await screen.findByTestId("env-card-grid");
    for (const id of ["p1", "p2", "p3", "p4", "p5"]) {
      expect(screen.getByTestId(`env-action-delete-${id}`)).toBeInTheDocument();
    }
  });

  // t078 AC-002（review test f004）：删除弹窗层面的 Escape 关闭与
  // 焦点回收，不只依赖共享 Dialog 的通用用例。
  it("closes the delete dialog on Escape without sending a request", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    fireEvent.click(screen.getByTestId("env-action-delete-p1"));
    await screen.findByTestId("env-delete-dialog");
    expect(stub.spies.profiles.createDeletions).not.toHaveBeenCalled();

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByTestId("env-delete-dialog")).toBeNull(),
    );
    expect(stub.spies.profiles.createDeletions).not.toHaveBeenCalled();
    // 焦点不留在已卸载的弹窗内，回到文档层级。
    expect(document.body.contains(document.activeElement)).toBe(true);
    expect(
      document.activeElement?.closest("[data-testid='env-delete-dialog']"),
    ).toBeNull();
  });

  it("keeps failed targets selected with stage, error and a working retry", async () => {
    stub = makeStub({
      ...fixture(),
      deletionFailAt: { p2: "cleaning" },
    });
    renderPage();
    await screen.findByTestId("env-table");
    selectRow("p1");
    selectRow("p2");
    await screen.findByTestId("env-batch-bar");
    fireEvent.click(screen.getByTestId("env-batch-delete"));
    fireEvent.click(await screen.findByTestId("env-delete-accept"));

    await waitFor(
      () =>
        expect(
          screen.getByTestId("env-delete-stage-p2").textContent,
        ).toContain(en.envDeleteStageFailed),
      { timeout: 5000 },
    );
    expect(screen.getByTestId("env-delete-error-p2").textContent).toContain(
      "simulated deletion failure",
    );
    expect(screen.getByTestId("env-delete-stage-p2").textContent).toContain(
      en.envDeleteStageCleaning,
    );

    fireEvent.click(screen.getByTestId("env-delete-retry-p2"));
    await waitFor(() =>
      expect(stub.spies.profiles.retryDeletion).toHaveBeenCalledWith(
        "op-p2",
      ),
    );
    await waitFor(
      () =>
        expect(
          screen.getByTestId("env-delete-stage-p2").textContent,
        ).toContain(en.envDeleteStageDone),
      { timeout: 5000 },
    );
    fireEvent.click(screen.getByTestId("env-delete-close"));
    await waitFor(() =>
      expect(screen.queryByTestId("env-delete-dialog")).toBeNull(),
    );
    expect(checkedState("p1")).toBe("false");
    expect(checkedState("p2")).toBe("false");
  });

  it("keeps failed targets selected after the dialog closes while succeeded ones clear", async () => {
    stub = makeStub({
      ...fixture(),
      deletionFailAt: { p2: "stopping" },
    });
    renderPage();
    await screen.findByTestId("env-table");
    selectRow("p1");
    selectRow("p2");
    await screen.findByTestId("env-batch-bar");
    fireEvent.click(screen.getByTestId("env-batch-delete"));
    fireEvent.click(await screen.findByTestId("env-delete-accept"));
    await waitFor(
      () =>
        expect(
          screen.getByTestId("env-delete-stage-p2").textContent,
        ).toContain(en.envDeleteStageFailed),
      { timeout: 5000 },
    );
    fireEvent.click(screen.getByTestId("env-delete-close"));
    await waitFor(() =>
      expect(screen.queryByTestId("env-delete-dialog")).toBeNull(),
    );
    expect(checkedState("p1")).toBe("false");
    expect(checkedState("p2")).toBe("true");
  });

  it("sends nothing when the single-delete dialog is cancelled", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    fireEvent.click(screen.getByTestId("env-action-delete-p2"));
    await screen.findByTestId("env-delete-dialog");
    expect(screen.getByTestId("env-delete-target-p2")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("env-delete-cancel"));
    await waitFor(() =>
      expect(screen.queryByTestId("env-delete-dialog")).toBeNull(),
    );
    expect(stub.spies.profiles.createDeletions).not.toHaveBeenCalled();
    expect(stub.spies.profiles.delete).not.toHaveBeenCalled();
  });
});

// t073 AC-005/006: 图标化操作栏、红色删除、宽编辑弹窗与差分更新。
describe("EnvironmentListPage t073 操作栏与宽编辑弹窗", () => {
  // t078 AC-001: 旧用例断言运行行没有删除按钮（停止/删除互斥的已废止
  // 语义），故整体替换为停止与删除并存、删除固定最右的新语义用例。
  it("运行行仅 1 个带文字主按钮，停止与删除并存且删除固定最右为 danger", async () => {
    renderPage();
    await screen.findByTestId("env-table");

    const row = screen.getByTestId("env-row-p1");
    const textButtons = within(row)
      .getAllByRole("button")
      .filter((button) => (button.textContent ?? "").trim().length > 0);
    expect(textButtons).toHaveLength(1);
    expect(textButtons[0]!.textContent).toContain(en.envOpen);
    expect(screen.getByTestId("env-action-details-p1")).toHaveAttribute(
      "aria-label",
      en.envDetails,
    );
    expect(screen.getByTestId("env-action-edit-p1")).toHaveAttribute(
      "aria-label",
      en.envEdit,
    );
    expect(screen.getByTestId("env-action-copy-p1")).toHaveAttribute(
      "aria-label",
      en.envDuplicate,
    );
    expect(screen.getByTestId("env-action-stop-p1").className).toContain(
      "text-warning",
    );
    const deleteButton = screen.getByTestId("env-action-delete-p1");
    expect(deleteButton.className).toContain("text-danger");
    expect(deleteButton).toHaveAttribute("title", en.envDeleteHintRunning);
    // 删除是操作区最后一个按钮（最右）。
    const rowButtons = within(row).getAllByRole("button");
    expect(rowButtons[rowButtons.length - 1]).toBe(deleteButton);
  });

  it("停止行显示红色 danger 删除图标按钮，主按钮为启动", async () => {
    renderPage();
    await screen.findByTestId("env-table");

    const row = screen.getByTestId("env-row-p2");
    const textButtons = within(row)
      .getAllByRole("button")
      .filter((button) => (button.textContent ?? "").trim().length > 0);
    expect(textButtons).toHaveLength(1);
    expect(textButtons[0]!.textContent).toContain(en.envStart);
    expect(screen.getByTestId("env-action-delete-p2").className).toContain(
      "text-danger",
    );
    expect(screen.queryByTestId("env-action-stop-p2")).toBeNull();
  });

  it("点击编辑弹出宽弹窗，保存走差分更新", async () => {
    renderPage();
    await screen.findByTestId("env-table");
    fireEvent.click(screen.getByTestId("env-action-edit-p1"));

    const dialog = await screen.findByTestId("env-edit-dialog");
    expect(dialog.closest('[role="dialog"]')?.className).toContain(
      "max-w-dialog-lg",
    );
    fireEvent.change(within(dialog).getByTestId("profile-form-name"), {
      target: { value: "Alpha renamed" },
    });
    fireEvent.click(within(dialog).getByTestId("profile-form-submit"));

    await waitFor(() =>
      expect(stub.spies.profiles.update).toHaveBeenCalledTimes(1),
    );
    const calls = (
      stub.spies.profiles.update as unknown as {
        mock: { calls: unknown[][] };
      }
    ).mock.calls;
    expect(calls[0]![1]).toMatchObject({ name: "Alpha renamed" });
    expect(Object.keys(calls[0]![1] as object)).toEqual(["name"]);
  });
});
