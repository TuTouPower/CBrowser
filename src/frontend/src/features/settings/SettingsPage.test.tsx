import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SettingsPage } from "./SettingsPage";
import { ProfileNewPage } from "../profiles/ProfileNewPage";
import { defaultApiClient } from "../../shared/api/client";
import { I18nProvider } from "../../i18n";

function renderPages() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <SettingsPage />
          <ProfileNewPage />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nProvider>
  );
}

describe("settings and profile form i18n", () => {
  beforeEach(() => {
    localStorage.setItem("cbm.locale", "zh");
    vi.spyOn(defaultApiClient.health, "check").mockResolvedValue(undefined);
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("switches every previously hardcoded label and placeholder", async () => {
    renderPages();

    expect(screen.getByText("系统网关与控制 API")).toBeTruthy();
    expect(screen.getByText("v2 API 服务状态")).toBeTruthy();
    expect(screen.getByPlaceholderText("例如：工作配置")).toBeTruthy();
    expect(screen.getByText("代理 URL（可选）")).toBeTruthy();
    expect(
      screen.getAllByText("标签（逗号分隔）").length
    ).toBeGreaterThan(0);
    await waitFor(() => expect(screen.getByText("正常")).toBeTruthy());

    fireEvent.click(screen.getByText("English"));

    expect(screen.getByText("System Gateway & Control API")).toBeTruthy();
    expect(screen.getByText("Status of v2 API services")).toBeTruthy();
    expect(screen.getByPlaceholderText("e.g. Work Profile")).toBeTruthy();
    expect(screen.getByText("Proxy URL (optional)")).toBeTruthy();
    expect(screen.getByText("Width (px)")).toBeTruthy();
    expect(
      screen.getAllByText("Tags (comma separated)").length
    ).toBeGreaterThan(0);
  });
});
