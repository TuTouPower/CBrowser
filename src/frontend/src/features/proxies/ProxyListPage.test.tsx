import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider, en } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ToastProvider } from "../../shared/ui";
import { ApiError, type ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import type { ProxyResponse } from "../../shared/api/types";
import { filterProxies, ProxyListPage } from "./ProxyListPage";

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
    used_by_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...rest,
  };
}

function fixture(): ProxyResponse[] {
  return [
    proxy({ id: "px1", used_by_count: 2 }),
    proxy({
      id: "px2",
      name: "EU Proxy",
      scheme: "http",
      host: "10.0.0.1",
      port: 8080,
      username: "eu-user",
      has_password: true,
      credential_revision: 2,
      country_code: "DE",
      country_name: "Germany",
      city: "Berlin",
      region_label: "Berlin",
      notes: "primary",
      used_by_count: 0,
    }),
    proxy({
      id: "px3",
      name: "Backup HTTPS",
      scheme: "https",
      host: "proxy.example.com",
      port: 443,
      country_code: "JP",
      region_label: "Tokyo",
      used_by_count: 0,
    }),
    proxy({
      id: "px4",
      name: "Home Socks",
      scheme: "socks5",
      host: "192.168.1.50",
      port: 1081,
      username: "home",
      has_password: true,
      credential_revision: 3,
      country_code: null,
      region_label: null,
      used_by_count: 1,
    }),
  ];
}

type LooseMock = ReturnType<typeof vi.fn>;

function mockFn(impl: (...args: any[]) => unknown): LooseMock {
  return vi.fn(impl) as unknown as LooseMock;
}

function makeStub(proxies: ProxyResponse[] = fixture()) {
  const spies = {
    proxies: {
      list: mockFn(async () => proxies),
      // t076 AC-001: the page reads the bounded server page; the stub
      // emulates the server contract (search/scheme/country_code/city/
      // name sort/paging) so filter tests still exercise the page.
      listCollection: mockFn(async (params: Record<string, unknown>) => {
        let items = [...proxies];
        const search = (params.search as string | undefined)?.toLowerCase();
        if (search) {
          items = items.filter((item) =>
            [
              item.name,
              item.host,
              item.country_name ?? "",
              item.city ?? "",
              item.region_label ?? "",
            ].some((value) => value.toLowerCase().includes(search)),
          );
        }
        const scheme = params.scheme as string | undefined;
        if (scheme) items = items.filter((item) => item.scheme === scheme);
        const countryCode = params.country_code as string | undefined;
        if (countryCode) {
          items = items.filter((item) => item.country_code === countryCode);
        }
        const city = params.city as string | undefined;
        if (city) items = items.filter((item) => item.city === city);
        items.sort((a, b) => a.name.localeCompare(b.name));
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
      listCountries: mockFn(async () => {
        const byCode = new Map<
          string,
          { country_code: string; country_name: string | null; cities: string[] }
        >();
        for (const item of proxies) {
          if (!item.country_code) continue;
          const entry = byCode.get(item.country_code) ?? {
            country_code: item.country_code,
            country_name: item.country_name ?? null,
            cities: [],
          };
          if (item.city && !entry.cities.includes(item.city)) {
            entry.cities.push(item.city);
          }
          byCode.set(item.country_code, entry);
        }
        return [...byCode.values()].map((entry) => ({
          ...entry,
          cities: [...entry.cities].sort(),
        }));
      }),
      get: mockFn(async () => proxies[0]!),
      getUsedBy: mockFn(async () => ({ proxy_id: "", entries: [] })),
      create: mockFn(async () => proxies[0]!),
      update: mockFn(async () => proxies[0]!),
      remove: mockFn(async () => undefined),
      probe: mockFn(async () => proxies[0]!),
    },
    profiles: {
      list: mockFn(async () => []),
      getRuntime: mockFn(async () => ({ observed_state: "stopped" })),
      getRuntimeSummary: mockFn(async () => ({ entries: [], running_count: 0 })),
    },
    groups: { list: mockFn(async () => []) },
    fontSets: { list: mockFn(async () => ({ items: [], default_font_set_id: { windows: null, macos: null } })) },
  };
  return { client: spies as unknown as ApiClient, spies, proxies };
}

let stub: ReturnType<typeof makeStub>;

function renderPage() {
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
            <ApiClientContext.Provider value={stub.client}>
              <MemoryRouter initialEntries={["/proxies"]}>
                <ProxyListPage />
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

function renderPageWithProfileRoute(initialEntries = ["/proxies"]) {
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
            <ApiClientContext.Provider value={stub.client}>
              <MemoryRouter initialEntries={initialEntries}>
                <Routes>
                  <Route path="/proxies" element={<ProxyListPage />} />
                  <Route
                    path="/profiles/:profileId/config"
                    element={<div data-testid="profile-detail-stub" />}
                  />
                </Routes>
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

function rowIds(): string[] {
  return Array.from(
    document.querySelectorAll('[data-testid^="proxy-row-"]'),
  ).map((node) => node.getAttribute("data-testid") ?? "");
}

async function chooseOption(testId: string, label: string) {
  const filter = screen.getByTestId(testId);
  fireEvent.click(within(filter).getByRole("combobox"));
  fireEvent.click(await screen.findByRole("option", { name: label }));
}

async function chooseScheme(label: string) {
  const filter = screen.getByTestId("proxy-scheme-filter");
  fireEvent.click(within(filter).getByRole("combobox"));
  fireEvent.click(await screen.findByRole("option", { name: label }));
}

beforeEach(() => {
  localStorage.clear();
  stub = makeStub();
});

describe("ProxyListPage AC-001 列展示", () => {
  it("renders eight independent columns and separate country/city/status cells", async () => {
    renderPage();
    await screen.findByTestId("proxy-table");
    expect(document.querySelectorAll("thead th")).toHaveLength(8);
    for (const key of [
      "proxyColName",
      "proxyColScheme",
      "proxyColAddress",
      "proxyColCountry",
      "proxyColCity",
      "proxyColStatus",
      "proxyColUsedBy",
      "proxyColActions",
    ] as const) {
      expect(screen.getByText(en[key])).toBeInTheDocument();
    }
    expect(screen.queryByText(en.proxyColRegion)).toBeNull();

    const px1 = screen.getByTestId("proxy-row-px1");
    expect(px1.textContent).toContain("US Proxy");
    expect(px1.textContent).toContain("socks5");
    expect(px1.textContent).toContain("1.2.3.4:1080");
    // t079 AC-005: the country cell shows flag + name, not the raw
    // letter code as a badge.
    expect(px1.textContent).toContain("🇺🇸");
    expect(within(px1).getByTestId("proxy-status-px1")).toHaveTextContent(
      en.proxyAvailable,
    );

    const px2 = screen.getByTestId("proxy-row-px2");
    expect(px2.textContent).toContain("10.0.0.1:8080");
    expect(px2.textContent).toContain("Germany");
    expect(px2.textContent).toContain("Berlin");
    expect(px2.textContent).toContain("🇩🇪");
    expect(screen.getByTestId("proxy-note-trigger-px2")).toHaveAttribute(
      "aria-label",
      "primary",
    );
  });

  it("supports switching between list and card layouts", async () => {
    renderPage();
    await screen.findByTestId("proxy-table");
    fireEvent.click(screen.getByTestId("proxy-layout-card"));
    expect(await screen.findByTestId("proxy-card-grid")).toBeInTheDocument();
    expect(screen.queryByTestId("proxy-table")).toBeNull();
    fireEvent.click(screen.getByTestId("proxy-layout-list"));
    expect(await screen.findByTestId("proxy-table")).toBeInTheDocument();
  });

  it("shows an empty state when the list is empty", async () => {
    stub = makeStub([]);
    renderPage();
    expect(await screen.findByTestId("proxy-list-page")).toBeInTheDocument();
    expect(await screen.findByTestId("empty-state")).toHaveTextContent(
      en.proxyEmpty,
    );
    expect(screen.queryByTestId("proxy-table")).toBeNull();
  });

  it("shows an error state instead of an empty table when loading fails", async () => {
    stub.spies.proxies.listCollection.mockRejectedValueOnce(
      new Error("proxies down"),
    );
    renderPage();
    expect(await screen.findByTestId("proxy-list-load-error")).toHaveTextContent(
      "proxies down",
    );
    expect(await screen.findByTestId("proxy-list-empty-error")).toBeInTheDocument();
    expect(screen.queryByTestId("proxy-table")).toBeNull();
    expect(screen.queryByTestId("empty-state")).toBeNull();
  });
});

describe("ProxyListPage 搜索、协议与位置筛选", () => {
  it("filters by name, host and region label (case-insensitive)", async () => {
    renderPage();
    await screen.findByTestId("proxy-table");
    const search = screen.getByTestId("proxy-search");

    fireEvent.change(search, { target: { value: "EU" } });
    await waitFor(() => expect(rowIds()).toEqual(["proxy-row-px2"]));

    fireEvent.change(search, { target: { value: "10.0.0.1" } });
    await waitFor(() => expect(rowIds()).toEqual(["proxy-row-px2"]));

    fireEvent.change(search, { target: { value: "Tokyo" } });
    await waitFor(() => expect(rowIds()).toEqual(["proxy-row-px3"]));

    fireEvent.change(search, { target: { value: "CALIFORNIA" } });
    await waitFor(() => expect(rowIds()).toEqual(["proxy-row-px1"]));
  });

  it("combines protocol filter with search through the toolbar Select", async () => {
    renderPage();
    await screen.findByTestId("proxy-table");
    fireEvent.change(screen.getByTestId("proxy-search"), {
      target: { value: "Proxy" },
    });
    await waitFor(() =>
      // t076 AC-001: the collection endpoint sorts by name by default;
      // "Backup HTTPS" matches via its host proxy.example.com.
      expect(rowIds()).toEqual([
        "proxy-row-px3",
        "proxy-row-px2",
        "proxy-row-px1",
      ]),
    );

    await chooseScheme("HTTP");
    await waitFor(() => expect(rowIds()).toEqual(["proxy-row-px2"]));
  });

  it("filterProxies combines scheme, country, city and query", () => {
    // Replaces the old "region" assertion: t074 splits location into
    // independent country/city filters persisted in URL search params.
    const proxies = fixture();
    const base = {
      q: "",
      scheme: "all" as const,
      country: "all",
      city: "all",
    };
    expect(
      filterProxies(proxies, { ...base, q: "proxy" }).map((item) => item.id),
    ).toEqual(["px1", "px2", "px3"]);
    expect(
      filterProxies(proxies, {
        ...base,
        q: "proxy",
        scheme: "http",
      }).map((item) => item.id),
    ).toEqual(["px2"]);
    expect(
      filterProxies(proxies, { ...base, country: "Germany" }).map(
        (item) => item.id,
      ),
    ).toEqual(["px2"]);
    expect(
      filterProxies(proxies, { ...base, city: "Berlin" }).map((item) => item.id),
    ).toEqual(["px2"]);
    expect(
      filterProxies(proxies, { ...base, scheme: "socks5" }).map(
        (item) => item.id,
      ),
    ).toEqual(["px1", "px4"]);
  });

  it("restores q/scheme/country/city from URL search params on reload", async () => {
    // t076 AC-001: the country URL param now carries the country code
    // (the collection filter matches codes, not display names).
    renderPageWithProfileRoute([
      "/proxies?q=EU&scheme=http&country=DE&city=Berlin",
    ]);
    await screen.findByTestId("proxy-table");
    await waitFor(() => expect(rowIds()).toEqual(["proxy-row-px2"]));
  });

  it("filters independently by country and city through linked toolbar selects", async () => {
    renderPage();
    await screen.findByTestId("proxy-table");

    // t079 AC-004/AC-005: country options carry flag + name (identity
    // stays the country code), so selection uses the new labels.
    await chooseOption("proxy-country-filter", "🇩🇪 Germany");
    await waitFor(() => expect(rowIds()).toEqual(["proxy-row-px2"]));

    await chooseOption("proxy-city-filter", "Berlin");
    await waitFor(() => expect(rowIds()).toEqual(["proxy-row-px2"]));

    await chooseOption("proxy-country-filter", "🇺🇸 US");
    await waitFor(() => expect(rowIds()).toEqual(["proxy-row-px1"]));
  });
});

describe("ProxyListPage t076 集合分页", () => {
  it("pages server-side from the collection endpoint", async () => {
    const many = Array.from({ length: 60 }, (_, index) =>
      proxy({
        id: `px-${index}`,
        name: `Proxy ${String(index).padStart(2, "0")}`,
        country_code: null,
        region_label: null,
      }),
    );
    stub = makeStub(many);
    renderPage();
    await screen.findByTestId("proxy-table");
    expect(rowIds()).toHaveLength(50);
    expect(
      stub.spies.proxies.listCollection.mock.calls[0]?.[0],
    ).toMatchObject({ page: 1, page_size: 50 });
    expect(stub.spies.proxies.listCountries).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("proxy-list-next-page"));
    await waitFor(() => expect(rowIds()).toHaveLength(10));
    const pages = stub.spies.proxies.listCollection.mock.calls.map(
      (call) => (call[0] as { page: number }).page,
    );
    expect(pages).toContain(2);
  });
});

describe("ProxyListPage AC-005 删除保护", () => {
  it("disables delete and shows proxyDeleteBlocked for used proxies", async () => {
    renderPage();
    await screen.findByTestId("proxy-table");

    const blocked = screen.getByTestId("proxy-row-px1");
    expect(screen.getByTestId("proxy-delete-px1")).toBeDisabled();
    expect(within(blocked).getByText(en.proxyDeleteBlocked)).toBeInTheDocument();

    expect(screen.getByTestId("proxy-delete-px4")).toBeDisabled();
    expect(screen.getByTestId("proxy-delete-px2")).not.toBeDisabled();
    expect(screen.getByTestId("proxy-delete-px3")).not.toBeDisabled();
  });

  it("confirms deletion and calls proxies.remove(id)", async () => {
    renderPage();
    await screen.findByTestId("proxy-table");
    fireEvent.click(screen.getByTestId("proxy-delete-px2"));

    const banner = await screen.findByTestId("proxy-delete-banner");
    expect(banner).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("proxy-delete-confirm"));

    await waitFor(() =>
      expect(stub.spies.proxies.remove).toHaveBeenCalledWith(
        "px2",
        expect.any(String),
      ),
    );
    expect(await screen.findByTestId("toast-item")).toHaveTextContent(
      en.proxyDeleteSuccess,
    );
    await waitFor(() =>
      expect(screen.queryByTestId("proxy-delete-banner")).toBeNull(),
    );
  });

  it("cancels deletion without calling proxies.remove", async () => {
    renderPage();
    await screen.findByTestId("proxy-table");
    fireEvent.click(screen.getByTestId("proxy-delete-px3"));
    await screen.findByTestId("proxy-delete-banner");
    fireEvent.click(screen.getByTestId("proxy-delete-cancel"));
    expect(screen.queryByTestId("proxy-delete-banner")).toBeNull();
    expect(stub.spies.proxies.remove).not.toHaveBeenCalled();
  });

  it("reads code/used_by_count from the 409 details and shows proxyInUse", async () => {
    stub.spies.proxies.remove.mockRejectedValueOnce(
      new ApiError(
        "Proxy is in use by 3 profiles",
        409,
        {
          error: "proxy_in_use",
          message: "Proxy is in use by 3 profiles",
          details: { used_by_count: 3 },
          retryable: false,
        },
        "proxy_in_use",
        false,
        { used_by_count: 3 },
      ),
    );
    renderPage();
    await screen.findByTestId("proxy-table");
    fireEvent.click(screen.getByTestId("proxy-delete-px2"));
    await screen.findByTestId("proxy-delete-banner");
    fireEvent.click(screen.getByTestId("proxy-delete-confirm"));

    const error = await screen.findByTestId("proxy-list-error");
    expect(error.textContent).toContain("3");
    expect(error.textContent).toContain("environments");
    expect(error.textContent).toContain(
      en.proxyInUse.replace("{count}", "3"),
    );
  });
});

describe("ProxyListPage AC-005 使用环境 0/1/2+ 交互", () => {
  function withUsedBy() {
    stub = makeStub(fixture());
    stub.spies.proxies.getUsedBy.mockImplementation(async (id: string) => {
      if (id === "px4") {
        return {
          proxy_id: id,
          entries: [{ profile_id: "p1", name: "Alpha", kind: "bound" }],
        };
      }
      if (id === "px1") {
        return {
          proxy_id: id,
          entries: [
            { profile_id: "p2", name: "Beta", kind: "current" },
            { profile_id: "p3", name: "Gamma", kind: "bound" },
          ],
        };
      }
      return { proxy_id: id, entries: [] };
    });
  }

  it("renders 0 as a non-interactive span and 1/2+ as buttons with counts only", async () => {
    withUsedBy();
    renderPage();
    await screen.findByTestId("proxy-table");

    const zero = screen.getByTestId("proxy-used-by-px2");
    expect(zero.tagName).toBe("SPAN");
    expect(zero).not.toHaveAttribute("href");
    expect(zero).toHaveTextContent(
      en.proxyUsedByCount.replace("{count}", "0"),
    );

    const one = screen.getByTestId("proxy-used-by-px4");
    expect(one.tagName).toBe("BUTTON");
    expect(one).toHaveTextContent(en.proxyUsedByCountOne);

    const many = screen.getByTestId("proxy-used-by-px1");
    expect(many.tagName).toBe("BUTTON");
    expect(many).toHaveTextContent(
      en.proxyUsedByCount.replace("{count}", "2"),
    );
  });

  it("navigates directly into the single environment for 1 used-by", async () => {
    withUsedBy();
    renderPageWithProfileRoute();
    await screen.findByTestId("proxy-table");
    fireEvent.click(screen.getByTestId("proxy-used-by-px4"));
    expect(await screen.findByTestId("profile-detail-stub")).toBeInTheDocument();
  });

  it("opens a popover listing every environment for 2+ used-by", async () => {
    withUsedBy();
    renderPageWithProfileRoute();
    await screen.findByTestId("proxy-table");
    fireEvent.click(screen.getByTestId("proxy-used-by-px1"));

    expect(
      await screen.findByTestId("proxy-used-by-popover"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("proxy-used-by-item-p2")).toHaveTextContent(
      "Beta",
    );
    expect(screen.getByTestId("proxy-used-by-item-p3")).toHaveTextContent(
      "Gamma",
    );

    fireEvent.click(screen.getByTestId("proxy-used-by-item-p2"));
    expect(await screen.findByTestId("profile-detail-stub")).toBeInTheDocument();
  });

  // t076 AC-004 (p122): a bound-only environment (current config moved
  // away, running instance still bound) is reachable from the count —
  // the old current-config-only derivation rendered it a dead span.
  // px4's single entry is bound-only here: the click must still
  // navigate straight to it, and the popover must label the kind.
  it("仅运行绑定占用的代理也可从计数进入该环境", async () => {
    withUsedBy();
    renderPageWithProfileRoute();
    await screen.findByTestId("proxy-table");
    fireEvent.click(screen.getByTestId("proxy-used-by-px1"));
    expect(
      await screen.findByTestId("proxy-used-by-popover"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("proxy-used-by-kind-p3")).toHaveTextContent(
      "running config",
    );
    fireEvent.click(screen.getByTestId("proxy-used-by-item-p3"));
    expect(await screen.findByTestId("profile-detail-stub")).toBeInTheDocument();
  });
});

describe("ProxyListPage 闪电测速与可用性检测 (t052+)", () => {
  it("shows a neutral not-probed status when observation_status is unknown", async () => {
    stub = makeStub([
      proxy({
        id: "px7",
        name: "Unprobed Proxy",
        country_code: null,
        observation_status: "unknown",
        region_label: null,
      }),
    ]);
    renderPage();
    await screen.findByTestId("proxy-table");
    const px7 = screen.getByTestId("proxy-row-px7");
    expect(within(px7).getByText(en.proxyStatusUnknown)).toBeInTheDocument();
  });

  it("shows a probing status while the observation is pending", async () => {
    stub = makeStub([
      proxy({
        id: "px9",
        name: "Pending Proxy",
        country_code: null,
        observation_status: "pending",
        region_label: null,
      }),
    ]);
    renderPage();
    await screen.findByTestId("proxy-table");
    const px9 = screen.getByTestId("proxy-row-px9");
    expect(within(px9).getByText(en.proxyStatusPending)).toBeInTheDocument();
    expect(
      within(px9).queryByText(en.proxyStatusUnknown),
    ).not.toBeInTheDocument();
  });

  it("renders successful latency in green and failed probe errors as localized text in red", async () => {
    stub = makeStub([
      proxy({
        id: "ok1",
        observation_status: "ok",
        latency_ms: 128,
        country_name: "United States",
        city: "Los Angeles",
      }),
      proxy({
        id: "bad1",
        observation_status: "failed",
        observation_error_code: "proxy_auth_failed",
      }),
    ]);
    renderPage();
    await screen.findByTestId("proxy-table");

    const ok = screen.getByTestId("proxy-status-ok1");
    expect(ok).toHaveTextContent("128ms");
    expect(ok.className).toContain("text-success");

    const bad = screen.getByTestId("proxy-status-bad1");
    // t079 AC-001: the main status shows the localized explanation for
    // the code; the raw machine code stays available for diagnostics
    // via the title, never as the primary text.
    expect(bad).toHaveTextContent(en.proxyErrorAuthFailed);
    expect(bad).not.toHaveTextContent("proxy_auth_failed");
    expect(bad).toHaveAttribute("title", "proxy_auth_failed");
    expect(bad.className).toContain("text-danger");
  });

  it("does not report success when HTTP 200 returns observation_status=failed", async () => {
    stub.spies.proxies.probe.mockResolvedValueOnce(
      proxy({
        id: "px4",
        observation_status: "failed",
        observation_error_code: "proxy_unreachable",
      }),
    );
    renderPage();
    await screen.findByTestId("proxy-table");
    fireEvent.click(screen.getByTestId("proxy-probe-px4"));

    expect(await screen.findByTestId("toast-item")).toHaveTextContent(
      en.proxyProbeFailed,
    );
  });

  it("calls proxies.probe(id) on single speed test and toasts success", async () => {
    renderPage();
    await screen.findByTestId("proxy-table");
    fireEvent.click(screen.getByTestId("proxy-probe-px4"));

    await waitFor(() =>
      expect(stub.spies.proxies.probe).toHaveBeenCalledWith("px4"),
    );
    expect(await screen.findByTestId("toast-item")).toHaveTextContent(
      en.proxyProbeSuccess,
    );
  });

  it("calls proxies.probe(id) for all visible proxies when clicking batch Zap button", async () => {
    renderPage();
    await screen.findByTestId("proxy-table");
    fireEvent.click(screen.getByTestId("proxy-probe-all"));

    await waitFor(() =>
      expect(stub.spies.proxies.probe).toHaveBeenCalledTimes(4),
    );
  });

  it("toasts failure when the speed test rejects", async () => {
    stub.spies.proxies.probe.mockRejectedValueOnce(new Error("probe down"));
    renderPage();
    await screen.findByTestId("proxy-table");
    fireEvent.click(screen.getByTestId("proxy-probe-px1"));

    expect(await screen.findByTestId("toast-item")).toHaveTextContent(
      en.proxyProbeFailed,
    );
  });
});

describe("ProxyListPage 编辑与新建弹窗", () => {
  it("opens the form dialog for add and edit", async () => {
    renderPage();
    await screen.findByTestId("proxy-table");

    fireEvent.click(screen.getByTestId("proxy-add"));
    const addDialog = await screen.findByRole("dialog");
    expect(within(addDialog).getByTestId("proxy-form-dialog")).toBeInTheDocument();
    expect(within(addDialog).getByText(en.proxyAdd)).toBeInTheDocument();
    fireEvent.click(within(addDialog).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    fireEvent.click(screen.getByTestId("proxy-edit-px2"));
    const editDialog = await screen.findByRole("dialog");
    expect(within(editDialog).getByTestId("proxy-form-dialog")).toBeInTheDocument();
    expect(within(editDialog).getByText(en.proxyEdit)).toBeInTheDocument();
  });
});
