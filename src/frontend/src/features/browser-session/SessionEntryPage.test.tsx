import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider, en } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ToastProvider } from "../../shared/ui";
import { type ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import type {
  ProfileResponse,
  ProfileRuntimeResponse,
} from "../../shared/api/types";
import { SessionEntryPage } from "./SessionEntryPage";
import { SESS_ENTRY_LINK, SESS_ENTRY_LIST, SESS_ENTRY_PAGE } from "./session_keys";

beforeAll(() => {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
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

function profile(overrides: Partial<ProfileResponse> = {}): ProfileResponse {
  return {
    id: "p1",
    name: "Alpha",
    display_number: 1,
    fingerprint_seed: 101,
    group_id: null,
    proxy_id: null,
    timezone: null,
    locale: null,
    screen_width: 1920,
    screen_height: 1080,
    gpu_family: "auto",
    humanize: false,
    human_preset: "default",
    geoip: true,
    clipboard_sync: true,
    auto_launch: false,
    color_scheme: null,
    fingerprint_platform: "windows",
    font_set_id: null,
    launch_args: [],
    extension_paths: [],
    allow_3p_cookies: true,
    set_google_default: true,
    capture_preview: true,
    restore_session: true,
    transparent_proxy: false,
    portable_cookies: false,
    notes: null,
    user_data_dir: "/data/p1",
    sort_order: 0,
    current_config_version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function runtime(
  profileId: string,
  observed: ProfileRuntimeResponse["observed_state"],
  overrides: Partial<ProfileRuntimeResponse> = {},
): ProfileRuntimeResponse {
  return {
    profile_id: profileId,
    display_number: 1,
    desired_state:
      observed === "running" || observed === "starting" ? "running" : "stopped",
    observed_state: observed,
    runtime_instance_id: "inst-1",
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    last_exit_event_id: null,
    last_started_at: observed === "running" ? "2026-01-01T10:00:00Z" : null,
    last_stopped_at: observed === "stopped" ? "2026-01-01T09:00:00Z" : null,
    last_coordinator_error: null,
    updated_at: "2026-01-01T10:00:00Z",
    ...overrides,
  };
}

function makeStub(
  profiles: ProfileResponse[],
  runtimes: Record<string, ProfileRuntimeResponse>,
): ApiClient {
  return {
    profiles: {
      list: vi.fn(async () => profiles),
      getRuntime: vi.fn(
        async (id: string) => runtimes[id] ?? runtime(id, "stopped"),
      ),
    },
  } as unknown as ApiClient;
}

function renderPage(client: ApiClient) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={client}>
              <MemoryRouter>
                <SessionEntryPage />
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
});

describe("SessionEntryPage", () => {
  it("lists only running environments as real session links with status", async () => {
    const profiles = [
      profile({ id: "p1", name: "Alpha" }),
      profile({ id: "p2", name: "Beta" }),
      profile({ id: "p3", name: "Gamma" }),
    ];
    const runtimes = {
      p1: runtime("p1", "running"),
      p2: runtime("p2", "stopped"),
      p3: runtime("p3", "error"),
    };
    renderPage(makeStub(profiles, runtimes));

    const links = await screen.findAllByTestId(SESS_ENTRY_LINK);
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAttribute("href", "/session/p1");
    expect(links[0]!.textContent).toContain("Alpha");
    expect(links[0]!.textContent).toContain(en.sessRunning);
    expect(screen.getByTestId(SESS_ENTRY_PAGE)).toBeInTheDocument();
    expect(screen.getByTestId(SESS_ENTRY_LIST)).toBeInTheDocument();
    expect(screen.queryByText("Beta")).toBeNull();
    expect(screen.queryByText("Gamma")).toBeNull();
  });

  it("shows the empty state when no environment is running", async () => {
    renderPage(
      makeStub(
        [profile({ id: "p1", name: "Alpha" })],
        { p1: runtime("p1", "stopped") },
      ),
    );

    await screen.findByText(en.sessEntryEmpty);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByTestId("empty-state").textContent).toContain(
      en.sessEntryHint,
    );
    expect(screen.queryAllByTestId(SESS_ENTRY_LINK)).toHaveLength(0);
  });
});
