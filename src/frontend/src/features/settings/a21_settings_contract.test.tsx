import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SettingsPage } from "./SettingsPage";
import { I18nProvider } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ApiClientContext } from "../../shared/api/client_context";
import type { ApiClient } from "../../shared/api/client";

function operation(overrides: Record<string, unknown> = {}) {
  return {
    operation_id: "op-1",
    target_version: 2,
    phase: "completed",
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

interface StubParts {
  client: ApiClient;
  request: ReturnType<typeof vi.fn>;
  fontSetsList: ReturnType<typeof vi.fn>;
  getSettings: ReturnType<typeof vi.fn>;
  updateSettings: ReturnType<typeof vi.fn>;
  checkDisconnect: ReturnType<typeof vi.fn>;
  apply: ReturnType<typeof vi.fn>;
  getOperation: ReturnType<typeof vi.fn>;
}

function makeClient(fontSetsReject = false): StubParts {
  const request = vi.fn(
    async (path: string, init?: RequestInit): Promise<unknown> => {
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
  const getSettings = vi.fn(async () => settings());
  const updateSettings = vi.fn(async () => ({ status: "ok" }));
  const checkDisconnect = vi.fn(async () => ({
    will_disconnect: false,
    new_entry_url: "https://127.0.0.1:56661",
  }));
  const apply = vi.fn(async () => operation({ phase: "rebuilding_caddy" }));
  const getOperation = vi.fn(async () => operation());
  const fontSetsList = vi.fn(async () => {
    if (fontSetsReject) throw new Error("font sets unavailable");
    return [];
  });
  const client = {
    request,
    network: {
      getSettings,
      updateSettings,
      checkDisconnect,
      apply,
      getOperation,
    },
    fontSets: { list: fontSetsList },
    health: { check: vi.fn(async () => undefined) },
  } as unknown as ApiClient;
  return {
    client,
    request,
    fontSetsList,
    getSettings,
    updateSettings,
    checkDisconnect,
    apply,
    getOperation,
  };
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

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("A21 settings page uses generated contract and unified query client", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("cbrowser.locale", "en");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
    localStorage.clear();
  });

  it("loads network settings and font sets through domain methods and query hooks", async () => {
    const { client, request, fontSetsList, getSettings } = makeClient();
    renderPage(client);
    await flush();

    expect(getSettings).toHaveBeenCalled();
    expect(fontSetsList).toHaveBeenCalled();
    expect(request).not.toHaveBeenCalledWith("/api/v1/font-sets");
    expect(request).not.toHaveBeenCalledWith("/api/v1/network/settings");
  });

  it("renders the shared font query error state", async () => {
    const { client, fontSetsList } = makeClient(true);
    renderPage(client);
    await waitFor(() =>
      expect(screen.getByTestId("font-sets-error")).toBeInTheDocument(),
    );
    expect(fontSetsList).toHaveBeenCalled();
  });

  it("saves pending config through the network domain method", async () => {
    const { client, request, updateSettings } = makeClient();
    renderPage(client);
    await flush();

    fireEvent.change(screen.getByTestId("https-port-input"), {
      target: { value: "58888" },
    });
    fireEvent.click(screen.getByTestId("save-network-btn"));
    await waitFor(() => expect(updateSettings).toHaveBeenCalled());

    expect(updateSettings).toHaveBeenCalledWith(
      expect.objectContaining({
        lan_access_enabled: false,
        lan_advertised_ip: null,
        https_port: 58888,
      }),
    );
    expect(request).not.toHaveBeenCalledWith(
      "/api/v1/network/settings",
      expect.objectContaining({ method: "PUT" }),
    );
  });
});
