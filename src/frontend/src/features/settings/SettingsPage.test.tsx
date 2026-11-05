import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SettingsPage } from "./SettingsPage";
import { ProfileNewPage } from "../profiles/ProfileNewPage";
import type { ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import { I18nProvider } from "../../i18n";

function renderPages() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  // Per-test stub injected at the ApiClient boundary (A22); the production
  // singleton is never mutated by tests.
  const stubClient = {
    health: { check: vi.fn(async () => undefined) },
    profiles: { create: vi.fn(async () => ({ id: "p-new" })) },
  } as unknown as ApiClient;
  return render(
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <ApiClientContext.Provider value={stubClient}>
          <MemoryRouter>
            <SettingsPage />
            <ProfileNewPage />
          </MemoryRouter>
        </ApiClientContext.Provider>
      </QueryClientProvider>
    </I18nProvider>
  );
}

describe("settings and profile form i18n (t035)", () => {
  beforeEach(() => {
    localStorage.setItem("cbm.locale", "zh");
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  // The old "switches every previously hardcoded label and placeholder"
  // case also asserted the four t035-removed tags/proxy labels; that whole
  // case was deleted. This new case keeps the i18n switch coverage for the
  // labels that still exist (AC-012 removal is not a reason to lose it).
  it("switches remaining i18n labels and placeholders", async () => {
    renderPages();

    expect(screen.getByText("控制 API")).toBeTruthy();
    expect(screen.getByText("控制 API 健康检查")).toBeTruthy();
    expect(screen.getByPlaceholderText("例如：工作配置")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("正常")).toBeTruthy());

    fireEvent.click(screen.getByText("English"));

    expect(screen.getByText("Control API")).toBeTruthy();
    expect(screen.getByText("Control API health check")).toBeTruthy();
    expect(screen.getByPlaceholderText("e.g. Work Profile")).toBeTruthy();
    expect(screen.getByText("Width (px)")).toBeTruthy();
  });
});
