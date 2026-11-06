import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SettingsPage } from "./SettingsPage";
import { ProfileForm } from "../profiles/ProfileForm";
import type { ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import { I18nProvider } from "../../i18n";
import { ThemeProvider } from "../../theme";

interface FontSetFixture {
  platform: string;
  set_id: string;
  source?: string | null;
  source_version?: string | null;
  integrity: { ok: boolean; problems?: string[] };
  file_count: number;
  used_by_count: number;
}

function renderPages(fontSets: FontSetFixture[] = []) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  // Per-test stub injected at the ApiClient boundary (A22); the production
  // singleton is never mutated by tests.
  const stubClient = {
    health: { check: vi.fn(async () => undefined) },
    profiles: { create: vi.fn(async () => ({ id: "p-new" })) },
    groups: { list: vi.fn(async () => []), create: vi.fn(async () => ({})) },
    proxies: { list: vi.fn(async () => []) },
    fontSets: { list: vi.fn(async () => []) },
    request: vi.fn(async () => fontSets),
  } as unknown as ApiClient;
  return render(
    <I18nProvider>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <ApiClientContext.Provider value={stubClient}>
            <MemoryRouter>
              <SettingsPage />
              <ProfileForm mode="create" onSubmit={async () => {}} />
            </MemoryRouter>
          </ApiClientContext.Provider>
        </QueryClientProvider>
      </ThemeProvider>
    </I18nProvider>,
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
    expect(screen.getByText("名称")).toBeTruthy();
    expect(screen.getByLabelText("宽度 (px)")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("正常")).toBeTruthy());

    fireEvent.click(screen.getByText("English"));

    expect(screen.getByText("Control API")).toBeTruthy();
    expect(screen.getByText("Control API health check")).toBeTruthy();
    expect(screen.getByText("Name")).toBeTruthy();
    expect(screen.getByLabelText("Width (px)")).toBeTruthy();
  });
});

describe("settings platform font sets (t036)", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders font set data from GET /api/v1/font-sets", async () => {
    renderPages([
      {
        platform: "windows",
        set_id: "win11",
        source: "Windows 11 Enterprise",
        source_version: "10.0.22631",
        integrity: { ok: true },
        file_count: 346,
        used_by_count: 2,
      },
    ]);

    const card = await screen.findByTestId("font-set-windows-win11");
    expect(card).toHaveTextContent("Windows 11 Enterprise");
    expect(card).toHaveTextContent("10.0.22631");
    expect(card).toHaveTextContent("346");
    expect(card).toHaveTextContent("2");
    expect(screen.queryByTestId("font-set-integrity-bad")).not.toBeInTheDocument();
  });

  it("shows an integrity warning for a font set with problems", async () => {
    renderPages([
      {
        platform: "macos",
        set_id: "pingfang",
        source: "macOS",
        source_version: "14",
        integrity: { ok: false, problems: ["missing: PingFang.ttc"] },
        file_count: 5,
        used_by_count: 0,
      },
    ]);

    const card = await screen.findByTestId("font-set-macos-pingfang");
    expect(card).toHaveTextContent("macOS");
    expect(screen.getByTestId("font-set-integrity-bad")).toBeInTheDocument();
    expect(screen.getByTestId("font-set-problems")).toHaveTextContent(
      "missing: PingFang.ttc",
    );
  });
});
