import { beforeAll, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider, en } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ToastProvider } from "../../shared/ui";
import { ApiError, type ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import type {
  ProxyCreateRequest,
  ProxyResponse,
  ProxyUpdateRequest,
} from "../../shared/api/types";
import { proxyKeys } from "../profiles/useProfilesQuery";
import { ProxyFormDialog } from "./ProxyFormDialog";

beforeAll(() => {
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

function proxyFixture(overrides: Partial<ProxyResponse> = {}): ProxyResponse {
  return {
    id: "px1",
    name: "US Proxy",
    scheme: "socks5",
    host: "1.2.3.4",
    port: 1080,
    username: null,
    has_password: false,
    credential_revision: 1,
    proxy_url: "socks5://1.2.3.4:1080",
    country_code: "US",
    egress_ip: "203.0.113.7",
    observation_status: "ok",
    observed_at: "2026-01-01T00:00:00Z",
    region_label: "California",
    notes: null,
    used_by_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

type LooseMock = ReturnType<typeof vi.fn>;

function mockFn(impl: (...args: any[]) => unknown): LooseMock {
  return vi.fn(impl) as unknown as LooseMock;
}

interface StubOptions {
  proxies?: ProxyResponse[];
  createImpl?: (
    data: ProxyCreateRequest,
    key?: string,
  ) => Promise<ProxyResponse>;
  updateImpl?: (
    proxyId: string,
    data: ProxyUpdateRequest,
    key?: string,
  ) => Promise<ProxyResponse>;
}

function makeStub(options: StubOptions = {}) {
  const spies = {
    proxies: {
      list: mockFn(async () => options.proxies ?? []),
      get: mockFn(async () => proxyFixture()),
      create: mockFn(options.createImpl ?? (async () => proxyFixture())),
      update: mockFn(options.updateImpl ?? (async () => proxyFixture())),
      remove: mockFn(async () => undefined),
      probe: mockFn(async () => proxyFixture()),
    },
  };
  return { client: spies as unknown as ApiClient, spies };
}

interface RenderOptions {
  proxy?: ProxyResponse | null;
  onOpenChange?: (open: boolean) => void;
  queryData?: ProxyResponse[];
}

function renderDialog(
  stub: ReturnType<typeof makeStub>,
  options: RenderOptions = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  if (options.queryData) {
    queryClient.setQueryData(proxyKeys.lists(), options.queryData);
  }
  const onOpenChange = options.onOpenChange ?? vi.fn();
  const view = render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={stub.client}>
              <MemoryRouter>
                <ProxyFormDialog
                  open
                  onOpenChange={onOpenChange}
                  proxy={options.proxy ?? null}
                />
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
  return { ...view, queryClient, onOpenChange };
}

function change(testId: string, value: string) {
  fireEvent.change(screen.getByTestId(testId), { target: { value } });
}

function click(testId: string) {
  fireEvent.click(screen.getByTestId(testId));
}

function openAdvanced() {
  click("proxy-form-advanced-toggle");
}

describe("ProxyFormDialog", () => {
  it("creates a proxy from a link, deriving the name as host:port", async () => {
    const stub = makeStub();
    const { onOpenChange } = renderDialog(stub);
    await screen.findByTestId("proxy-form-dialog");

    change("proxy-form-url", "socks5://user:pass@10.0.0.9:8080");
    click("proxy-form-submit");

    await waitFor(() =>
      expect(stub.spies.proxies.create).toHaveBeenCalledTimes(1),
    );
    const payload = stub.spies.proxies.create.mock.calls[0]![0] as ProxyCreateRequest;
    expect(payload.proxy_url).toBe("socks5://user:pass@10.0.0.9:8080");
    expect(payload.name).toBe("10.0.0.9:8080");
    expect(payload).not.toHaveProperty("password");
    expect(payload).not.toHaveProperty("country_code");
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(screen.getByTestId("toast-item")).toHaveTextContent(
      en.proxyCreateSuccess,
    );
  });

  it("disables the submit button while a create is in flight (t056 A23)", async () => {
    let resolveCreate!: (value: ProxyResponse) => void;
    const pending = new Promise<ProxyResponse>((resolve) => {
      resolveCreate = resolve;
    });
    const stub = makeStub({ createImpl: () => pending });
    const { onOpenChange } = renderDialog(stub);
    await screen.findByTestId("proxy-form-dialog");

    change("proxy-form-url", "socks5://user:pass@10.0.0.9:8080");
    click("proxy-form-submit");
    await waitFor(() =>
      expect(stub.spies.proxies.create).toHaveBeenCalledTimes(1),
    );
    expect(screen.getByTestId("proxy-form-submit")).toBeDisabled();
    // A second click while disabled must not start a second create.
    click("proxy-form-submit");
    expect(stub.spies.proxies.create).toHaveBeenCalledTimes(1);

    resolveCreate(proxyFixture());
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(stub.spies.proxies.create).toHaveBeenCalledTimes(1);
  });

  it("shows only link, notes and read-only country status by default", async () => {
    const stub = makeStub();
    renderDialog(stub, { proxy: proxyFixture() });
    await screen.findByTestId("proxy-form-dialog");

    expect(screen.getByTestId("proxy-form-url")).toBeInTheDocument();
    expect(screen.getByTestId("proxy-form-notes")).toBeInTheDocument();
    expect(screen.getByTestId("proxy-form-country-status")).toHaveTextContent(
      "US",
    );
    expect(screen.queryByTestId("proxy-form-name")).toBeNull();
    expect(screen.queryByTestId("proxy-form-host")).toBeNull();
    expect(screen.queryByTestId("proxy-form-country-code")).toBeNull();

    openAdvanced();
    expect(screen.getByTestId("proxy-form-name")).toBeInTheDocument();
    expect(screen.getByTestId("proxy-form-host")).toBeInTheDocument();
  });

  it("shows unknown country status when there is no valid observation", async () => {
    const stub = makeStub();
    renderDialog(stub);
    await screen.findByTestId("proxy-form-dialog");

    expect(screen.getByTestId("proxy-form-country-status")).toHaveTextContent(
      en.proxyCountryUnknown,
    );
  });

  it("shows detecting country status while the observation is pending", async () => {
    // test f003: pending (detecting) must not read as unknown.
    const stub = makeStub();
    renderDialog(stub, {
      proxy: proxyFixture({
        observation_status: "pending",
        country_code: null,
        egress_ip: null,
      }),
    });
    await screen.findByTestId("proxy-form-dialog");

    const status = screen.getByTestId("proxy-form-country-status");
    expect(status).toHaveTextContent(en.proxyCountryProbing);
    expect(status).not.toHaveTextContent(en.proxyCountryUnknown);
  });

  it("syncs link and advanced fields both ways", async () => {
    const stub = makeStub();
    renderDialog(stub);
    await screen.findByTestId("proxy-form-dialog");

    change("proxy-form-url", "socks5://user:pass@10.0.0.1:1080");
    openAdvanced();
    expect(screen.getByTestId("proxy-form-host")).toHaveValue("10.0.0.1");
    expect(screen.getByTestId("proxy-form-port")).toHaveValue("1080");
    expect(screen.getByTestId("proxy-form-username")).toHaveValue("user");
    expect(screen.getByTestId("proxy-form-password")).toHaveValue("pass");
    // The derived name follows the parse while it was never typed by hand.
    expect(screen.getByTestId("proxy-form-name")).toHaveValue("10.0.0.1:1080");

    change("proxy-form-host", "10.0.0.2");
    // While the link input holds focus it shows the full link (so a later
    // parse keeps the password); blurring switches to the redacted display.
    expect(screen.getByTestId("proxy-form-url")).toHaveValue(
      "socks5://user:pass@10.0.0.2:1080",
    );
    fireEvent.blur(screen.getByTestId("proxy-form-url"));
    expect(screen.getByTestId("proxy-form-url")).toHaveValue(
      "socks5://user@10.0.0.2:1080",
    );

    click("proxy-form-submit");
    await waitFor(() =>
      expect(stub.spies.proxies.create).toHaveBeenCalledTimes(1),
    );
    const payload = stub.spies.proxies.create.mock.calls[0]![0] as ProxyCreateRequest;
    expect(payload.proxy_url).toBe("socks5://user:pass@10.0.0.2:1080");
  });

  it("keeps a manually typed name across later link parses", async () => {
    const stub = makeStub();
    renderDialog(stub);
    await screen.findByTestId("proxy-form-dialog");

    change("proxy-form-url", "socks5://user:pass@10.0.0.1:1080");
    openAdvanced();
    change("proxy-form-name", "Keep me");
    change("proxy-form-url", "http://10.0.0.9:3128");

    expect(screen.getByTestId("proxy-form-name")).toHaveValue("Keep me");
    click("proxy-form-submit");
    await waitFor(() =>
      expect(stub.spies.proxies.create).toHaveBeenCalledTimes(1),
    );
    const payload = stub.spies.proxies.create.mock.calls[0]![0] as ProxyCreateRequest;
    expect(payload.name).toBe("Keep me");
    expect(payload.proxy_url).toBe("http://10.0.0.9:3128");
  });

  it("shows an error for an invalid link and keeps the parsed fields", async () => {
    const stub = makeStub();
    renderDialog(stub);
    await screen.findByTestId("proxy-form-dialog");

    change("proxy-form-url", "socks5://user:pass@10.0.0.1:1080");
    change("proxy-form-notes", "note");
    change("proxy-form-url", "not-a-url");

    expect(screen.getByTestId("proxy-form-url-error")).toHaveTextContent(
      en.proxyUrlInvalid,
    );
    openAdvanced();
    expect(screen.getByTestId("proxy-form-host")).toHaveValue("10.0.0.1");
    expect(screen.getByTestId("proxy-form-port")).toHaveValue("1080");
    expect(screen.getByTestId("proxy-form-notes")).toHaveValue("note");

    click("proxy-form-submit");
    expect(stub.spies.proxies.create).not.toHaveBeenCalled();
  });

  it("blocks submission when the link is empty", async () => {
    const stub = makeStub();
    renderDialog(stub);
    await screen.findByTestId("proxy-form-dialog");

    click("proxy-form-submit");

    expect(screen.getByTestId("proxy-form-url-error")).toBeInTheDocument();
    expect(screen.getByTestId("proxy-form-error")).toBeInTheDocument();
    expect(stub.spies.proxies.create).not.toHaveBeenCalled();
  });

  it("omits proxy_url from the update payload when the endpoint is untouched", async () => {
    const stub = makeStub();
    renderDialog(stub, { proxy: proxyFixture({ has_password: true }) });
    await screen.findByTestId("proxy-form-dialog");

    click("proxy-form-submit");

    await waitFor(() =>
      expect(stub.spies.proxies.update).toHaveBeenCalledTimes(1),
    );
    const data = stub.spies.proxies.update.mock.calls[0]![1] as ProxyUpdateRequest;
    expect(data).not.toHaveProperty("proxy_url");
    expect(data).not.toHaveProperty("password");
    expect(data.name).toBe("US Proxy");
  });

  it("blocks an endpoint change that would silently clear a stored password", async () => {
    const stub = makeStub();
    renderDialog(stub, {
      proxy: proxyFixture({
        has_password: true,
        username: "alice",
        proxy_url: "socks5://alice@1.2.3.4:1080",
      }),
    });
    await screen.findByTestId("proxy-form-dialog");

    openAdvanced();
    change("proxy-form-host", "10.0.0.5");
    click("proxy-form-submit");

    expect(
      screen.getByTestId("proxy-form-password-error"),
    ).toHaveTextContent(en.proxyPasswordRequiredOnEndpointChange);
    expect(stub.spies.proxies.update).not.toHaveBeenCalled();

    change("proxy-form-password", "newpass");
    click("proxy-form-submit");
    await waitFor(() =>
      expect(stub.spies.proxies.update).toHaveBeenCalledTimes(1),
    );
    const data = stub.spies.proxies.update.mock.calls[0]![1] as ProxyUpdateRequest;
    expect(data.proxy_url).toBe("socks5://alice:newpass@10.0.0.5:1080");
  });

  it("sends a password-less link when the clear-password button is used", async () => {
    const stub = makeStub();
    renderDialog(stub, {
      proxy: proxyFixture({
        has_password: true,
        username: "alice",
        proxy_url: "socks5://alice@1.2.3.4:1080",
      }),
    });
    await screen.findByTestId("proxy-form-dialog");

    openAdvanced();
    click("proxy-form-clear-password");
    click("proxy-form-submit");

    await waitFor(() =>
      expect(stub.spies.proxies.update).toHaveBeenCalledTimes(1),
    );
    const data = stub.spies.proxies.update.mock.calls[0]![1] as ProxyUpdateRequest;
    expect(data.proxy_url).toBe("socks5://alice@1.2.3.4:1080");
    expect(data.proxy_url).not.toContain("pass");
  });

  it("never writes a stored password into state, DOM or query cache", async () => {
    const secret = "STORED_SECRET_9f3";
    const leaked = {
      ...proxyFixture({ has_password: true }),
      password: secret,
    } as ProxyResponse;
    const stub = makeStub();
    const { queryClient } = renderDialog(stub, {
      proxy: leaked,
      queryData: [proxyFixture({ has_password: true })],
    });
    await screen.findByTestId("proxy-form-dialog");

    openAdvanced();
    expect(screen.getByTestId("proxy-form-password")).toHaveValue("");
    expect(document.body.textContent).not.toContain(secret);
    const listCache = JSON.stringify(queryClient.getQueryData(proxyKeys.lists()));
    expect(listCache).not.toContain(secret);
    expect(listCache).not.toContain('"password"');

    click("proxy-form-submit");
    await waitFor(() =>
      expect(stub.spies.proxies.update).toHaveBeenCalledTimes(1),
    );
    const allCache = JSON.stringify(
      queryClient.getQueryCache().getAll().map((query) => query.state.data),
    );
    expect(allCache).not.toContain(secret);
    expect(allCache).not.toContain('"password"');
  });

  it("surfaces a readable message for a 409 ApiError with an object detail", async () => {
    const detail = { code: "proxy_in_use", count: 2 };
    const stub = makeStub({
      updateImpl: async () => {
        throw new ApiError(
          "Conflict",
          409,
          { detail },
          undefined,
          false,
          detail,
        );
      },
    });
    renderDialog(stub, { proxy: proxyFixture() });
    await screen.findByTestId("proxy-form-dialog");

    click("proxy-form-submit");

    await waitFor(() =>
      expect(screen.getByTestId("proxy-form-banner")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("proxy-form-banner")).toHaveTextContent(
      "proxy_in_use",
    );
  });

  it("rejects username and region_label longer than 255 characters", async () => {
    const stub = makeStub();
    renderDialog(stub);
    await screen.findByTestId("proxy-form-dialog");

    change("proxy-form-url", "http://10.0.0.9:8080");
    openAdvanced();
    change("proxy-form-username", "u".repeat(256));
    change("proxy-form-region-label", "r".repeat(256));
    click("proxy-form-submit");

    await screen.findByTestId("proxy-form-username-error");
    expect(
      screen.getByTestId("proxy-form-region-label-error"),
    ).toBeInTheDocument();
    expect(stub.spies.proxies.create).not.toHaveBeenCalled();
  });
});
