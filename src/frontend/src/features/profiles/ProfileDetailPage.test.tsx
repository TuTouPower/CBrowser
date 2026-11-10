import { beforeAll, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider, en } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ToastProvider } from "../../shared/ui";
import { ApiClientContext } from "../../shared/api/client_context";
import type { ApiClient } from "../../shared/api/client";
import type {
  ProfileResponse,
  ProfileRuntimeResponse,
} from "../../shared/api/types";
import { ProfileDetailPage } from "./ProfileDetailPage";

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
        static fromRect() {
          return new DOMRect();
        }
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
  if (!HTMLElement.prototype.hasPointerCapture) {
    HTMLElement.prototype.hasPointerCapture = () => false;
  }
  if (!HTMLElement.prototype.setPointerCapture) {
    HTMLElement.prototype.setPointerCapture = () => undefined;
  }
  if (!HTMLElement.prototype.releasePointerCapture) {
    HTMLElement.prototype.releasePointerCapture = () => undefined;
  }
});

function profile(): ProfileResponse {
  return {
    id: "p1",
    name: "Profile Alpha",
    display_number: 1,
    fingerprint_seed: 101,
    group_id: "g1",
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
  };
}

function runtime(observed: string): ProfileRuntimeResponse {
  return {
    profile_id: "p1",
    display_number: 1,
    desired_state: observed === "running" ? "running" : "stopped",
    observed_state: observed,
    runtime_instance_id: "inst_1",
    config_version: 2,
    failure_count: 0,
    restart_blocked: false,
    last_exit_event_id: null,
    updated_at: "2026-01-01T00:00:00Z",
    search_defaults: {
      state: "failed",
      error_kind: "timeout",
      runtime_instance_id: "inst_1",
      request_id: null,
      updated_at: "2026-01-01T00:00:00Z",
    },
  } as unknown as ProfileRuntimeResponse;
}

function makeStub(observed = "running") {
  return {
    profiles: {
      get: vi.fn(async () => profile()),
      getRuntime: vi.fn(async () => runtime(observed)),
      list: vi.fn(async () => [profile()]),
      update: vi.fn(async () => profile()),
      delete: vi.fn(async () => undefined),
      duplicate: vi.fn(async () => profile()),
      reset: vi.fn(async () => profile()),
      retrySearchDefaults: vi.fn(async () => runtime(observed)),
      setDesiredState: vi.fn(async () => runtime(observed)),
      stop: vi.fn(async () => runtime(observed)),
    },
    groups: {
      list: vi.fn(async () => [
        {
          id: "g1",
          name: "Work",
          color: "slate",
          sort_order: 0,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ]),
    },
    proxies: { list: vi.fn(async () => []) },
    fontSets: { list: vi.fn(async () => []) },
  } as unknown as ApiClient & {
    profiles: {
      retrySearchDefaults: ReturnType<typeof vi.fn>;
      setDesiredState: ReturnType<typeof vi.fn>;
      stop: ReturnType<typeof vi.fn>;
    };
  };
}

function renderPage(stub: ReturnType<typeof makeStub>) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={stub}>
              <MemoryRouter initialEntries={["/profiles/p1/config"]}>
                <Routes>
                  <Route
                    path="/profiles/:profileId/:tab"
                    element={<ProfileDetailPage />}
                  />
                </Routes>
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

const STATUS_CASES: Array<[string, string]> = [
  ["starting", en.statusStarting],
  ["stopping", en.statusStopping],
  ["running", en.statusRunning],
  ["error", en.statusError],
  ["stopped", en.statusStopped],
];

describe("ProfileDetailPage", () => {
  for (const [observed, label] of STATUS_CASES) {
    it(`shows the ${observed} status with its text`, async () => {
      renderPage(makeStub(observed));
      await waitFor(() =>
        expect(screen.getByTestId("profile-detail-status").textContent).toBe(
          label,
        ),
      );
      if (observed === "running") {
        expect(screen.getByTestId("profile-detail-number").textContent).toBe(
          "#0001",
        );
      }
    });
  }

  it("renders four real tab anchors", async () => {
    renderPage(makeStub());
    await screen.findByTestId("profile-detail-tabs");
    for (const tab of ["config", "files", "automation", "maintenance"]) {
      expect(screen.getByTestId(`profile-tab-${tab}`).getAttribute("href")).toBe(
        `/profiles/p1/${tab}`,
      );
    }
  });

  it("offers start and stop actions", async () => {
    const stub = makeStub("stopped");
    renderPage(stub);

    await screen.findByTestId("profile-detail-start");
    fireEvent.click(screen.getByTestId("profile-detail-start"));
    await waitFor(() =>
      expect(stub.profiles.setDesiredState).toHaveBeenCalledWith(
        "p1",
        "running",
        expect.any(String),
      ),
    );

    fireEvent.click(screen.getByTestId("profile-detail-stop"));
    await waitFor(() =>
      expect(stub.profiles.stop).toHaveBeenCalledWith("p1", expect.any(String)),
    );
  });

  it("shows both shared banners on the config tab", async () => {
    const stub = makeStub("running");
    renderPage(stub);

    const failed = await screen.findByTestId("profile-search-defaults-failed");
    expect(failed).toBeInTheDocument();
    expect(await screen.findByTestId("profile-apply-pending")).toBeInTheDocument();

    fireEvent.click(within(failed).getByRole("button"));
    await waitFor(() =>
      expect(stub.profiles.retrySearchDefaults).toHaveBeenCalledWith(
        "p1",
        expect.any(String),
      ),
    );
  });

  it("runtime failure does not block the config tab", async () => {
    const stub = makeStub("running");
    (stub.profiles.getRuntime as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("runtime down"),
    );
    renderPage(stub);

    // P2: runtime 失败降级为顶栏 Banner，配置页仍可访问。
    expect(await screen.findByTestId("profile-detail-runtime-error")).toHaveTextContent(
      "runtime down",
    );
    expect(screen.getByTestId("profile-detail-view")).toBeInTheDocument();
    expect(screen.getByTestId("profile-config-tab")).toBeInTheDocument();
    expect(screen.queryByTestId("profile-detail-error")).toBeNull();
  });
});
