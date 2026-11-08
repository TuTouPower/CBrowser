import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router";
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
  return {
    id: "px1",
    name: "US Proxy",
    scheme: "socks5",
    host: "1.2.3.4",
    port: 1080,
    username: null,
    has_password: false,
    credential_revision: 1,
    country_code: "US",
    region_label: "California",
    notes: null,
    used_by_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
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
      get: mockFn(async () => proxies[0]!),
      create: mockFn(async () => proxies[0]!),
      update: mockFn(async () => proxies[0]!),
      remove: mockFn(async () => undefined),
    },
    profiles: { list: mockFn(async () => []) },
    groups: { list: mockFn(async () => []) },
    fontSets: { list: mockFn(async () => []) },
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

function rowIds(): string[] {
  return Array.from(
    document.querySelectorAll('[data-testid^="proxy-row-"]'),
  ).map((node) => node.getAttribute("data-testid") ?? "");
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
  it("renders the seven columns with name, protocol, address, auth, region, used-by and actions", async () => {
    renderPage();
    await screen.findByTestId("proxy-table");
    expect(document.querySelectorAll("thead th")).toHaveLength(7);
    for (const key of [
      "proxyColName",
      "proxyColScheme",
      "proxyColAddress",
      "proxyColAuth",
      "proxyColRegion",
      "proxyColUsedBy",
      "proxyColActions",
    ] as const) {
      expect(screen.getByText(en[key])).toBeInTheDocument();
    }

    const px1 = screen.getByTestId("proxy-row-px1");
    expect(px1.textContent).toContain("US Proxy");
    expect(px1.textContent).toContain("socks5");
    expect(px1.textContent).toContain("1.2.3.4:1080");
    expect(within(px1).getByText(en.proxyAuthNo)).toBeInTheDocument();
    expect(px1.textContent).toContain("US");
    expect(px1.textContent).toContain("California");
    expect(px1.textContent).toContain("2");

    const px2 = screen.getByTestId("proxy-row-px2");
    expect(within(px2).getByText(en.proxyAuthYes)).toBeInTheDocument();
    expect(px2.textContent).toContain("10.0.0.1:8080");
    expect(px2.textContent).toContain("Berlin");
    expect(px2.textContent).toContain("DE");
  });

  it("shows an empty state when the list is empty", async () => {
    stub = makeStub([]);
    renderPage();
    expect(await screen.findByTestId("proxy-list-page")).toBeInTheDocument();
    expect(screen.getByTestId("empty-state")).toHaveTextContent(en.proxyEmpty);
    expect(screen.queryByTestId("proxy-table")).toBeNull();
  });
});

describe("ProxyListPage 搜索与协议筛选", () => {
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
      expect(rowIds()).toEqual([
        "proxy-row-px1",
        "proxy-row-px2",
        "proxy-row-px3",
      ]),
    );

    await chooseScheme("HTTP");
    await waitFor(() => expect(rowIds()).toEqual(["proxy-row-px2"]));
  });

  it("filterProxies combines scheme and query and matches name/host/region", () => {
    const proxies = fixture();
    expect(
      filterProxies(proxies, "proxy", "all").map((item) => item.id),
    ).toEqual(["px1", "px2", "px3"]);
    expect(
      filterProxies(proxies, "proxy", "http").map((item) => item.id),
    ).toEqual(["px2"]);
    expect(
      filterProxies(proxies, "", "socks5").map((item) => item.id),
    ).toEqual(["px1", "px4"]);
    expect(
      filterProxies(proxies, "berlin", "socks5").map((item) => item.id),
    ).toEqual([]);
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

  it("reads code/used_by_count from the 409 detail and shows proxyInUse", async () => {
    stub.spies.proxies.remove.mockRejectedValueOnce(
      new ApiError("Conflict", 409, {
        detail: { code: "proxy_in_use", used_by_count: 3 },
      }),
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

describe("ProxyListPage AC-006 使用环境数链接", () => {
  it("links to the environment list with ?proxy=<id>", async () => {
    renderPage();
    await screen.findByTestId("proxy-table");
    expect(screen.getByTestId("proxy-used-by-px1").getAttribute("href")).toContain(
      "?proxy=px1",
    );
    expect(screen.getByTestId("proxy-used-by-px3").getAttribute("href")).toContain(
      "?proxy=px3",
    );
  });

  it("encodes the id in the used-by link", async () => {
    stub = makeStub([proxy({ id: "px/a b" })]);
    renderPage();
    await screen.findByTestId("proxy-table");
    const href = screen
      .getByTestId("proxy-used-by-px/a b")
      .getAttribute("href");
    expect(href).toContain("?proxy=");
    expect(href).not.toContain(" ");
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
