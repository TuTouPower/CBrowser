import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SettingsPage } from "./SettingsPage";
import { I18nProvider } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ApiClientContext } from "../../shared/api/client_context";
import { ApiClient } from "../../shared/api/client";

function renderWithProviders(client: ApiClient) {
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
    </I18nProvider>
  );
}

describe("SettingsPage Network Access Block", () => {
  let mockClient: any;

  beforeEach(() => {
    mockClient = new ApiClient();
    vi.spyOn(mockClient, "request").mockImplementation((...args: unknown[]) => {
      const path = args[0] as string;
      const options = args[1] as { method?: string } | undefined;
      if (path === "/api/v1/font-sets") {
        return Promise.resolve({ items: [], default_font_set_id: { windows: null, macos: null } });
      }
      if (path === "/api/v1/network/settings") {
        if (options?.method === "PUT") {
          return Promise.resolve({ status: "ok" });
        }
        return Promise.resolve({
          pending_config: { lan_access_enabled: false, lan_advertised_ip: null },
          applied_version: {
            version: 1,
            config: { lan_access_enabled: false, lan_advertised_ip: null },
            applied_at: "2026-11-08T00:00:00+08:00",
            caddyfile_sha256: "",
            origin_whitelist: ["https://127.0.0.1:56661"],
          },
          active_operation: null,
        });
      }
      if (path === "/api/v1/network/check-disconnect") {
        return Promise.resolve({
          will_disconnect: false,
          new_entry_url: "https://127.0.0.1:56661",
        });
      }
      if (path === "/api/v1/network/apply") {
        return Promise.resolve({
          operation_id: "op-test-1",
          target_version: 2,
          phase: "rebuilding_caddy",
          created_at: "2026-11-08T00:00:00+08:00",
          updated_at: "2026-11-08T00:00:00+08:00",
        });
      }
      return Promise.resolve({});
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders network access settings and displays applied status", async () => {
    renderWithProviders(mockClient);

    // Network section title
    expect(await screen.findByText(/Network Access|网络访问/i)).toBeInTheDocument();

    // Status badges
    const statusBadges = await screen.findAllByText(/127.0.0.1/);
    expect(statusBadges.length).toBeGreaterThanOrEqual(1);

    // Toggle switch
    const toggle = screen.getByTestId("lan-access-toggle");
    expect(toggle).toBeInTheDocument();
    expect(toggle).not.toBeChecked();

    // Root CA download link
    const caLink = screen.getByTestId("download-root-ca-btn");
    expect(caLink).toBeInTheDocument();
    expect(caLink.getAttribute("href")).toBe("/api/v1/network/root-ca");
  });

  it("allows toggling LAN access, entering IP and saving pending changes", async () => {
    renderWithProviders(mockClient);

    const toggle = await screen.findByTestId("lan-access-toggle");
    fireEvent.click(toggle);
    expect(toggle).toBeChecked();

    const ipInput = screen.getByTestId("lan-ip-input");
    expect(ipInput).toBeInTheDocument();
    fireEvent.change(ipInput, { target: { value: "192.168.31.76" } });

    const portInput = screen.getByTestId("https-port-input");
    expect(portInput).toBeInTheDocument();
    fireEvent.change(portInput, { target: { value: "58888" } });

    const saveBtn = screen.getByTestId("save-network-btn");
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(mockClient.request).toHaveBeenCalledWith(
        "/api/v1/network/settings",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({
            lan_access_enabled: true,
            lan_advertised_ip: "192.168.31.76",
            https_port: 58888,
          }),
        })
      );
    });
  });
});
