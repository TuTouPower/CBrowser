import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SettingsPage } from "./SettingsPage";
import { I18nProvider } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ApiClientContext } from "../../shared/api/client_context";
import type { ApiClient } from "../../shared/api/client";

interface OperationShape {
  operation_id: string;
  target_version: number;
  phase: string;
  error_reason?: string | null;
  new_entry_url?: string | null;
  created_at: string;
  updated_at: string;
}

function operation(overrides: Partial<OperationShape> = {}): OperationShape {
  return {
    operation_id: "op-1",
    target_version: 2,
    phase: "rebuilding_caddy",
    error_reason: null,
    new_entry_url: "https://192.168.31.76:56661",
    created_at: "2026-11-08T00:00:00+08:00",
    updated_at: "2026-11-08T00:00:00+08:00",
    ...overrides,
  };
}

function settings() {
  return {
    pending_config: {
      lan_access_enabled: false,
      lan_advertised_ip: null,
      https_port: 56661,
    },
    applied_version: {
      version: 1,
      config: {
        lan_access_enabled: false,
        lan_advertised_ip: null,
        https_port: 56661,
      },
      bind_host: "127.0.0.1",
      applied_at: "2026-11-08T00:00:00+08:00",
      caddyfile_sha256: "",
      origin_whitelist: [],
    },
    active_operation: null,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function makeClient(responder: () => Promise<OperationShape>) {
  const requestCalls: Array<{ path: string; init?: RequestInit }> = [];
  const operationCalls: string[] = [];
  const request = vi.fn(
    async (path: string, init?: RequestInit): Promise<unknown> => {
      requestCalls.push({ path, init });
      if (path.startsWith("/api/v1/network/operations/")) {
        operationCalls.push(path);
        return responder();
      }
      if (path === "/api/v1/network/settings") {
        return init?.method === "PUT" ? { status: "ok" } : settings();
      }
      if (path === "/api/v1/network/check-disconnect") {
        return {
          will_disconnect: false,
          new_entry_url: "https://127.0.0.1:56661",
        };
      }
      if (path === "/api/v1/network/apply") return operation();
      if (path === "/api/v1/font-sets") return [];
      return {};
    },
  );
  const client = {
    request,
    network: {
      getSettings: vi.fn(async () => request("/api/v1/network/settings")),
      updateSettings: vi.fn(async (config: unknown) =>
        request("/api/v1/network/settings", {
          method: "PUT",
          body: JSON.stringify(config),
        }),
      ),
      checkDisconnect: vi.fn(async () =>
        request("/api/v1/network/check-disconnect"),
      ),
      apply: vi.fn(async (body: unknown) =>
        request("/api/v1/network/apply", {
          method: "POST",
          body: JSON.stringify(body),
        }),
      ),
      getOperation: vi.fn(async (id: string, signal?: AbortSignal) =>
        request(`/api/v1/network/operations/${id}`, { signal }),
      ),
    },
    fontSets: { list: vi.fn(async () => request("/api/v1/font-sets")) },
    health: { check: vi.fn(async () => request("/api/v1/health")) },
  } as unknown as ApiClient;
  return { client, requestCalls, operationCalls };
}

function renderPage(client: ApiClient) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <I18nProvider>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <ApiClientContext.Provider value={client}>
            <SettingsPage />
          </ApiClientContext.Provider>
        </QueryClientProvider>
      </ThemeProvider>
    </I18nProvider>,
  );
}

async function tick(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

async function startApply() {
  fireEvent.click(screen.getByTestId("apply-network-btn"));
  await tick(0);
  fireEvent.change(screen.getByTestId("admin-password-input"), {
    target: { value: "pw" },
  });
  fireEvent.click(screen.getByTestId("confirm-apply-btn"));
  await tick(0);
}

describe("A19 network apply operation polling lifecycle", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("cbrowser.locale", "en");
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    document.body.innerHTML = "";
    localStorage.clear();
  });

  it("stops polling after the component unmounts", async () => {
    const { client, operationCalls } = makeClient(async () => operation());
    const view = renderPage(client);
    await tick(0);
    await startApply();
    await tick(1000);
    expect(operationCalls.length).toBeGreaterThan(0);

    const before = operationCalls.length;
    view.unmount();
    await tick(60_000);
    expect(operationCalls.length).toBe(before);
  });

  it("never overlaps a slow in-flight operation request", async () => {
    const { client, operationCalls } = makeClient(
      () => new Promise<OperationShape>(() => {}),
    );
    renderPage(client);
    await tick(0);
    await startApply();
    await tick(60_000);
    expect(operationCalls.length).toBe(1);
  });

  it("stops at the deadline and surfaces a reconnect entry after sustained disconnects", async () => {
    const { client, operationCalls } = makeClient(async () => {
      throw new Error("connection lost");
    });
    renderPage(client);
    await tick(0);
    await startApply();
    await tick(60_000);

    expect(screen.getByTestId("network-apply-disconnected")).toBeInTheDocument();
    expect(screen.getByTestId("network-last-phase")).toHaveTextContent(
      "rebuilding_caddy",
    );
    expect(screen.getByTestId("network-reconnect-link")).toHaveAttribute(
      "href",
      "https://192.168.31.76:56661",
    );
    expect(operationCalls.length).toBeLessThan(40);
  });

  it("fences a late response after unmount", async () => {
    const pending = deferred<OperationShape>();
    const { client, requestCalls } = makeClient(() => pending.promise);
    const view = renderPage(client);
    await tick(0);
    await startApply();
    await tick(1000);

    const refreshesBefore = requestCalls.filter(
      (call) =>
        call.path === "/api/v1/network/settings" && !call.init?.method,
    ).length;
    view.unmount();
    pending.resolve(operation({ phase: "completed" }));
    await tick(0);
    const refreshesAfter = requestCalls.filter(
      (call) =>
        call.path === "/api/v1/network/settings" && !call.init?.method,
    ).length;
    expect(refreshesAfter).toBe(refreshesBefore);
  });

  it("ends polling immediately on a completed operation", async () => {
    const { client, operationCalls } = makeClient(async () =>
      operation({ phase: "completed" }),
    );
    renderPage(client);
    await tick(0);
    await startApply();
    await tick(10_000);
    expect(operationCalls.length).toBe(1);
    expect(screen.getByTestId("network-apply-success")).toBeInTheDocument();
  });

  it("ends polling immediately on a failed operation", async () => {
    const { client, operationCalls } = makeClient(async () =>
      operation({ phase: "failed", error_reason: "caddy rebuild failed" }),
    );
    renderPage(client);
    await tick(0);
    await startApply();
    await tick(10_000);
    expect(operationCalls.length).toBe(1);
    expect(screen.getByTestId("network-apply-error")).toBeInTheDocument();
  });

  it("surfaces the reconnect entry at the real 30s deadline under slow disconnecting requests", async () => {
    const slowMs = 10_000;
    const { client, operationCalls } = makeClient(
      () =>
        new Promise<OperationShape>((_resolve, reject) => {
          setTimeout(() => reject(new Error("connection lost")), slowMs);
        }),
    );
    renderPage(client);
    await tick(0);
    await startApply();
    await tick(60_000);

    expect(
      screen.getByTestId("network-apply-disconnected"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("network-last-phase")).toHaveTextContent(
      "rebuilding_caddy",
    );
    expect(screen.getByTestId("network-reconnect-link")).toHaveAttribute(
      "href",
      "https://192.168.31.76:56661",
    );
    expect(operationCalls.length).toBeLessThan(10);
  });
});
