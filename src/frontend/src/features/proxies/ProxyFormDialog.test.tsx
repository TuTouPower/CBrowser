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
    country_code: "US",
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

describe("ProxyFormDialog", () => {
  it("creates a proxy with a correctly typed request payload", async () => {
    const stub = makeStub();
    const { onOpenChange } = renderDialog(stub);
    await screen.findByTestId("proxy-form-dialog");

    change("proxy-form-name", "Edge Proxy");
    change("proxy-form-host", "10.0.0.9");
    change("proxy-form-port", "8080");
    click("proxy-form-submit");

    await waitFor(() =>
      expect(stub.spies.proxies.create).toHaveBeenCalledTimes(1),
    );
    expect(stub.spies.proxies.create).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Edge Proxy",
        scheme: "http",
        host: "10.0.0.9",
        port: 8080,
      }),
      expect.any(String),
    );
    const payload = stub.spies.proxies.create.mock.calls[0]![0] as ProxyCreateRequest;
    expect(typeof payload.port).toBe("number");
    expect(payload).not.toHaveProperty("password");
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(screen.getByTestId("toast-item")).toHaveTextContent(
      en.proxyCreateSuccess,
    );
  });

  it("omits password from the update payload when it is left blank", async () => {
    const stub = makeStub();
    renderDialog(stub, { proxy: proxyFixture({ has_password: true }) });
    await screen.findByTestId("proxy-form-dialog");

    click("proxy-form-submit");

    await waitFor(() =>
      expect(stub.spies.proxies.update).toHaveBeenCalledTimes(1),
    );
    const data = stub.spies.proxies.update.mock.calls[0]![1] as ProxyUpdateRequest;
    expect(data).not.toHaveProperty("password");
    expect(data).toMatchObject({
      name: "US Proxy",
      scheme: "socks5",
      host: "1.2.3.4",
      port: 1080,
    });
  });

  it("sends password null when the clear-password button is used", async () => {
    const stub = makeStub();
    renderDialog(stub, { proxy: proxyFixture({ has_password: true }) });
    await screen.findByTestId("proxy-form-dialog");

    click("proxy-form-clear-password");
    click("proxy-form-submit");

    await waitFor(() =>
      expect(stub.spies.proxies.update).toHaveBeenCalledTimes(1),
    );
    const data = stub.spies.proxies.update.mock.calls[0]![1] as ProxyUpdateRequest;
    expect(data.password).toBeNull();
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

  it("fills parsed fields from a valid URL without touching name/country/region/notes", async () => {
    const stub = makeStub();
    renderDialog(stub);
    await screen.findByTestId("proxy-form-dialog");

    change("proxy-form-name", "Keep me");
    change("proxy-form-country-code", "US");
    change("proxy-form-region-label", "California");
    change("proxy-form-notes", "note");
    change("proxy-paste-url-input", "socks5://user:pass@10.0.0.1:1080");
    click("proxy-paste-url-apply");

    expect(screen.getByTestId("proxy-form-host")).toHaveValue("10.0.0.1");
    expect(screen.getByTestId("proxy-form-port")).toHaveValue("1080");
    expect(screen.getByTestId("proxy-form-username")).toHaveValue("user");
    expect(screen.getByTestId("proxy-form-password")).toHaveValue("pass");
    expect(screen.getByTestId("proxy-form-name")).toHaveValue("Keep me");
    expect(screen.getByTestId("proxy-form-country-code")).toHaveValue("US");
    expect(screen.getByTestId("proxy-form-region-label")).toHaveValue(
      "California",
    );
    expect(screen.getByTestId("proxy-form-notes")).toHaveValue("note");
    expect(screen.queryByTestId("proxy-paste-url-error")).toBeNull();

    click("proxy-form-submit");
    await waitFor(() =>
      expect(stub.spies.proxies.create).toHaveBeenCalledTimes(1),
    );
    const payload = stub.spies.proxies.create.mock.calls[0]![0] as ProxyCreateRequest;
    expect(payload.scheme).toBe("socks5");
    expect(payload.name).toBe("Keep me");
    expect(payload.port).toBe(1080);
    expect(payload.country_code).toBe("US");
    expect(payload.region_label).toBe("California");
    expect(payload.notes).toBe("note");
  });

  it("shows an error for an invalid URL and keeps already-filled fields", async () => {
    const stub = makeStub();
    renderDialog(stub);
    await screen.findByTestId("proxy-form-dialog");

    change("proxy-form-name", "Keep me");
    change("proxy-form-host", "1.2.3.4");
    change("proxy-paste-url-input", "not-a-url");
    click("proxy-paste-url-apply");

    expect(screen.getByTestId("proxy-paste-url-error")).toHaveTextContent(
      en.proxyPasteUrlInvalid,
    );
    expect(screen.getByTestId("proxy-form-name")).toHaveValue("Keep me");
    expect(screen.getByTestId("proxy-form-host")).toHaveValue("1.2.3.4");
    expect(screen.getByTestId("proxy-form-port")).toHaveValue("");
  });

  it("blocks submission when the name is empty and shows field and summary errors", async () => {
    const stub = makeStub();
    renderDialog(stub);
    await screen.findByTestId("proxy-form-dialog");

    change("proxy-form-host", "1.2.3.4");
    change("proxy-form-port", "8080");
    click("proxy-form-submit");

    expect(screen.getByTestId("proxy-form-name-error")).toHaveTextContent(
      en.proxyNameRequired,
    );
    expect(screen.getByTestId("proxy-form-error")).toBeInTheDocument();
    expect(stub.spies.proxies.create).not.toHaveBeenCalled();
    expect(stub.spies.proxies.update).not.toHaveBeenCalled();
  });

  it("submits authenticated socks5 without any frontend blocking", async () => {
    const stub = makeStub();
    renderDialog(stub, {
      proxy: proxyFixture({ scheme: "socks5", has_password: false }),
    });
    await screen.findByTestId("proxy-form-dialog");

    change("proxy-form-username", "alice");
    change("proxy-form-password", "s3cret");
    click("proxy-form-submit");

    await waitFor(() =>
      expect(stub.spies.proxies.update).toHaveBeenCalledTimes(1),
    );
    const data = stub.spies.proxies.update.mock.calls[0]![1] as ProxyUpdateRequest;
    expect(data.scheme).toBe("socks5");
    expect(data.username).toBe("alice");
    expect(data.password).toBe("s3cret");
    expect(screen.queryByTestId("proxy-form-banner")).toBeNull();
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

    change("proxy-form-name", "Edge Proxy");
    change("proxy-form-host", "10.0.0.9");
    change("proxy-form-port", "8080");
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
