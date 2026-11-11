import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SettingsPage } from "./SettingsPage";
import { I18nProvider } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ApiClientContext } from "../../shared/api/client_context";
import type { ApiClient } from "../../shared/api/client";

/**
 * t054: the Settings network section is read-only. It shows the current
 * access address + port from window.location and states the port is fixed
 * at deploy time. There is no LAN toggle, no IP/port input, no save/apply
 * flow, no root-CA download, and the page makes no network-settings
 * request at all.
 */
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
    </I18nProvider>,
  );
}

describe("SettingsPage network section is read-only (t054)", () => {
  beforeEach(() => {
    localStorage.setItem("cbrowser.locale", "en");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("shows the current access address and port, and no form controls", async () => {
    const healthCheck = vi.fn(async () => undefined);
    const fontSetsList = vi.fn(async () => ({
      items: [],
      default_font_set_id: { windows: null, macos: null },
    }));
    const client = {
      health: { check: healthCheck },
      fontSets: {
        list: fontSetsList,
      },
    } as unknown as ApiClient;
    renderWithProviders(client);

    expect(await screen.findByText("Network Access")).toBeInTheDocument();
    expect(screen.getByTestId("network-current-address")).toHaveTextContent(
      window.location.origin,
    );
    expect(screen.getByTestId("network-current-port")).toHaveTextContent(
      window.location.port || "443",
    );
    expect(
      screen.getByText(/fixed at deploy time/i),
    ).toBeInTheDocument();

    for (const testId of [
      "lan-access-toggle",
      "lan-ip-input",
      "https-port-input",
      "save-network-btn",
      "apply-network-btn",
      "download-root-ca-btn",
      "apply-modal",
      "admin-password-input",
    ]) {
      expect(screen.queryByTestId(testId)).not.toBeInTheDocument();
    }

    // t054 R1 test f004: the old assertion spied on `client.request`,
    // which this page never calls, so it could never fail. Assert the
    // data paths the page actually uses instead — health + font sets —
    // so a regression that stops fetching them turns this test red.
    expect(healthCheck).toHaveBeenCalled();
    expect(fontSetsList).toHaveBeenCalled();
  });
});
