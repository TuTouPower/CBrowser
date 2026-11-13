import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SettingsPage } from "./SettingsPage";
import { I18nProvider } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ApiClientContext } from "../../shared/api/client_context";
import type { ApiClient } from "../../shared/api/client";

// t054: the network contract cases (load/save through the network domain
// method) are deleted with the runtime network surface; only the shared
// font-query error case survives — it never touched the network API.
function makeClient(fontSetsReject = false) {
  const fontSetsList = vi.fn(async () => {
    if (fontSetsReject) throw new Error("font sets unavailable");
    return { items: [], default_font_set_id: { windows: null, macos: null } };
  });
  const client = {
    request: vi.fn(async () => ({})),
    fontSets: { list: fontSetsList },
    health: { check: vi.fn(async () => undefined) },
  } as unknown as ApiClient;
  return { client, fontSetsList };
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

  it("renders the shared font query error state", async () => {
    const { client, fontSetsList } = makeClient(true);
    renderPage(client);
    await waitFor(() =>
      expect(screen.getByTestId("font-sets-error")).toBeInTheDocument(),
    );
    expect(fontSetsList).toHaveBeenCalled();
  });

});
