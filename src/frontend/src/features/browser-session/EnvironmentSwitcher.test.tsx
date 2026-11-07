import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider, en } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ToastProvider } from "../../shared/ui";
import { type ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import type {
  GroupResponse,
  ProfileResponse,
  ProfileRuntimeResponse,
} from "../../shared/api/types";
import {
  EnvironmentSwitcher,
  type EnvironmentSwitcherProps,
} from "./EnvironmentSwitcher";
import {
  SESS_SWITCHER_GROUP,
  SESS_SWITCHER_ITEM,
  SESS_SWITCHER_SEARCH,
  SESS_SWITCHER_TRIGGER,
  sessId,
} from "./session_keys";

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

function group(overrides: Partial<GroupResponse> = {}): GroupResponse {
  return {
    id: "g1",
    name: "Work",
    color: "blue",
    sort_order: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function runtime(
  profileId: string,
  observed: ProfileRuntimeResponse["observed_state"],
): ProfileRuntimeResponse {
  return {
    profile_id: profileId,
    desired_state: observed === "running" ? "running" : "stopped",
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
  };
}

function makeStub(
  runtimes: Record<string, ProfileRuntimeResponse>,
): ApiClient {
  return {
    profiles: {
      list: vi.fn(async () => []),
      getRuntime: vi.fn(
        async (id: string) => runtimes[id] ?? runtime(id, "stopped"),
      ),
    },
  } as unknown as ApiClient;
}

function renderSwitcher(props: EnvironmentSwitcherProps, client: ApiClient) {
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
                <EnvironmentSwitcher {...props} />
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

function fixture(): EnvironmentSwitcherProps {
  return {
    currentProfileId: "p1",
    profiles: [
      profile({ id: "p1", name: "Alpha", group_id: "g1" }),
      profile({ id: "p2", name: "Beta", group_id: "g1" }),
      profile({ id: "p3", name: "Gamma", group_id: null }),
    ],
    groups: [group({ id: "g1", name: "Work" })],
  };
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

describe("EnvironmentSwitcher", () => {
  it("groups environments and exposes real case-insensitive searchable links", async () => {
    const props = fixture();
    renderSwitcher(props, makeStub({ p1: runtime("p1", "running") }));

    const trigger = screen.getByTestId(SESS_SWITCHER_TRIGGER);
    expect(trigger.textContent).toContain("Alpha");
    await waitFor(() =>
      expect(trigger.textContent).toContain(en.sessRunning),
    );

    fireEvent.click(trigger);
    const search = await screen.findByTestId(SESS_SWITCHER_SEARCH);

    const headers = screen
      .getAllByTestId(SESS_SWITCHER_GROUP)
      .map((node) => node.textContent);
    expect(headers).toContain("Work");
    expect(headers).toContain(en.sessUngrouped);

    expect(screen.getAllByTestId(SESS_SWITCHER_ITEM)).toHaveLength(3);
    for (const id of ["p1", "p2", "p3"]) {
      expect(screen.getByTestId(sessId("switcher-item", id))).toHaveAttribute(
        "href",
        `/session/${id}`,
      );
    }

    fireEvent.change(search, { target: { value: "aLpH" } });
    await waitFor(() =>
      expect(
        screen.getByTestId(sessId("switcher-item", "p1")),
      ).toBeInTheDocument(),
    );
    expect(
      screen.queryByTestId(sessId("switcher-item", "p2")),
    ).toBeNull();
    expect(
      screen.queryByTestId(sessId("switcher-item", "p3")),
    ).toBeNull();
    expect(screen.getAllByTestId(SESS_SWITCHER_ITEM)).toHaveLength(1);

    fireEvent.change(search, { target: { value: "no-match" } });
    await screen.findByText(en.sessSwitcherEmpty);
    expect(screen.queryAllByTestId(SESS_SWITCHER_ITEM)).toHaveLength(0);
  });

  it("closes the popover on Escape via the Radix dismissable layer", async () => {
    const props = fixture();
    renderSwitcher(props, makeStub({ p1: runtime("p1", "running") }));

    fireEvent.click(screen.getByTestId(SESS_SWITCHER_TRIGGER));
    await screen.findByRole("dialog");
    expect(screen.getByTestId(SESS_SWITCHER_TRIGGER)).toHaveAttribute(
      "data-state",
      "open",
    );

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() =>
      expect(screen.getByTestId(SESS_SWITCHER_TRIGGER)).toHaveAttribute(
        "data-state",
        "closed",
      ),
    );
    expect(screen.queryByTestId(SESS_SWITCHER_SEARCH)).toBeNull();
  });
});
