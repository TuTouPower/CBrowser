import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppLayout } from "./AppLayout";
import { I18nProvider } from "../i18n";
import { ThemeProvider } from "../theme";
import { ToastProvider } from "../shared/ui";
import { ApiClientContext } from "../shared/api/client_context";
import { profileKeys } from "../features/profiles/useProfilesQuery";
import type { ApiClient } from "../shared/api/client";
import type { ProfileResponse, ProfileRuntimeResponse } from "../shared/api/types";

vi.mock("../features/auth/useAuth", () => ({
  useAuth: () => ({ logout: vi.fn(async () => undefined) }),
}));

const PROFILES: ProfileResponse[] = [
  { id: "p1", name: "Alpha" } as ProfileResponse,
  { id: "p2", name: "Beta" } as ProfileResponse,
];

function runtimeFor(id: string, observed = "stopped", error: string | null = null) {
  return {
    profile_id: id,
    display_number: 1,
    desired_state: observed,
    observed_state: observed,
    runtime_instance_id: null,
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    last_exit_event_id: null,
    last_coordinator_error: error,
    updated_at: "2026-01-01T00:00:00Z",
  } as ProfileRuntimeResponse;
}

function installMatchMedia(narrow: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      get matches() {
        if (query === "(max-width: 1023px)") return narrow;
        return false;
      },
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  });
}

function renderShell() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const client = {
    profiles: {
      list: vi.fn(async () => PROFILES),
      getRuntime: vi.fn(async (id: string) => runtimeFor(id)),
      update: vi.fn(async () => PROFILES[0]),
    },
  } as unknown as ApiClient;
  const view = render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={client}>
              <MemoryRouter initialEntries={["/"]}>
                <AppLayout />
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
  return { ...view, queryClient, client };
}

describe("AppLayout shell contract (t036)", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    installMatchMedia(false);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("restores collapsed and width from localStorage on mount", async () => {
    localStorage.setItem("cbrowser.sidebar.collapsed", "1");
    localStorage.setItem("cbrowser.sidebar.width", "300");
    const view = renderShell();
    const sidebar = await view.findByTestId("sidebar");
    expect(sidebar.parentElement).toHaveStyle({ width: "72px" });

    fireEvent.click(screen.getByRole("button", { name: "Expand sidebar" }));
    await waitFor(() =>
      expect(sidebar.parentElement).toHaveStyle({ width: "300px" }),
    );
    expect(localStorage.getItem("cbrowser.sidebar.collapsed")).toBe("0");
  });

  it("clamps resize to 200-360px and persists the width", async () => {
    const view = renderShell();
    const handle = await view.findByTestId("sidebar-resize-handle");
    fireEvent.pointerDown(handle, { clientX: 100 });
    fireEvent.pointerMove(window, { clientX: 5000 });
    fireEvent.pointerUp(window);
    await waitFor(() =>
      expect(localStorage.getItem("cbrowser.sidebar.width")).toBe("360"),
    );

    fireEvent.pointerDown(handle, { clientX: 100 });
    fireEvent.pointerMove(window, { clientX: -5000 });
    fireEvent.pointerUp(window);
    await waitFor(() =>
      expect(localStorage.getItem("cbrowser.sidebar.width")).toBe("200"),
    );
  });

  it("uses a drawer on narrow layouts", async () => {
    installMatchMedia(true);
    const view = renderShell();
    const open = await view.findByRole("button", { name: "Open navigation" });
    expect(view.queryByTestId("sidebar")).not.toBeInTheDocument();
    fireEvent.click(open);
    expect(await view.findByTestId("sidebar-drawer")).toBeInTheDocument();
    fireEvent.click(view.getByRole("button", { name: "Close navigation" }));
    await waitFor(() =>
      expect(view.queryByTestId("sidebar-drawer")).not.toBeInTheDocument(),
    );
  });

  it("updates the running count and coordinator banner from SSE runtime data", async () => {
    const view = renderShell();
    expect(await view.findByTestId("running-count")).toBeInTheDocument();
    await waitFor(() =>
      expect(view.client.profiles.getRuntime).toHaveBeenCalledTimes(2),
    );
    expect(view.getByTestId("running-count")).toHaveTextContent("0");

    act(() => {
      view.queryClient.setQueryData(
        profileKeys.runtime("p1"),
        runtimeFor("p1", "running", "coordinator unreachable"),
      );
    });
    await waitFor(() =>
      expect(view.getByTestId("running-count")).toHaveTextContent("1"),
    );
    const banner = await view.findByTestId("runtime-coordinator-error");
    expect(banner).toHaveAttribute("role", "alert");
    expect(banner).toHaveTextContent("coordinator unreachable");
  });

  it("switching the UI theme never writes a Profile color_scheme", async () => {
    const view = renderShell();
    await view.findByTestId("sidebar");
    fireEvent.pointerDown(view.getByRole("button", { name: "Switch theme" }), {
      button: 0,
      ctrlKey: false,
    });
    await screen.findByRole("menu");
    const lightItem = screen.getAllByRole("menuitem").find((item) => item.textContent?.includes("Light"));
    expect(lightItem).toBeDefined();
    fireEvent.click(lightItem!);
    await waitFor(() => expect(localStorage.getItem("cbrowser.theme")).toBe("light"));
    expect(document.documentElement.classList.contains("light")).toBe(true);
    expect(view.client.profiles.update).not.toHaveBeenCalled();
  });
});
