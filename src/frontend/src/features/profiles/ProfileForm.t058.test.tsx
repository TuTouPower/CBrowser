import { beforeAll, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider, en } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ToastProvider } from "../../shared/ui";
import { ApiClientContext } from "../../shared/api/client_context";
import type { ApiClient } from "../../shared/api/client";
import type {
  FontSetInfo,
  GroupResponse,
  ProfileCreateRequest,
  ProfileResponse,
  ProfileUpdateRequest,
  ProxyResponse,
} from "../../shared/api/types";
import { ProfileForm } from "./ProfileForm";

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
  if (typeof Element.prototype.hasPointerCapture !== "function") {
    Element.prototype.hasPointerCapture = () => false;
    Element.prototype.releasePointerCapture = () => undefined;
  }
});

function group(): GroupResponse {
  return {
    id: "g1",
    name: "Work",
    color: "slate",
    sort_order: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function proxy(): ProxyResponse {
  return {
    id: "px1",
    name: "Proxy A",
    scheme: "http",
    host: "proxy.example",
    port: 8080,
    username: null,
    has_password: false,
    credential_revision: 1,
    proxy_url: "http://proxy.example:8080",
    country_code: "US",
    observation_status: "ok",
    region_label: null,
    notes: null,
    used_by_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function profile(overrides: Partial<ProfileResponse> = {}): ProfileResponse {
  return {
    id: "p1",
    name: "Original",
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

function makeStub() {
  return {
    groups: { list: vi.fn(async () => [group()]) },
    proxies: { list: vi.fn(async () => [proxy()]) },
    fontSets: {
      list: vi.fn(async () => ({
        items: [] as FontSetInfo[],
        default_font_set_id: { windows: null, macos: null },
      })),
    },
  } as unknown as ApiClient;
}

function renderForm(opts: {
  mode: "create" | "edit";
  initial?: ProfileResponse;
  onSubmit?: (
    values: ProfileCreateRequest | ProfileUpdateRequest,
  ) => Promise<void>;
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={makeStub()}>
              <MemoryRouter>
                <ProfileForm
                  mode={opts.mode}
                  initial={opts.initial}
                  onSubmit={opts.onSubmit ?? (async () => undefined)}
                />
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

function changeTimezone(value: string) {
  fireEvent.focus(screen.getByTestId("profile-form-timezone"));
  fireEvent.change(screen.getByTestId("profile-form-timezone"), {
    target: { value },
  });
  fireEvent.keyDown(screen.getByTestId("profile-form-timezone"), {
    key: "Enter",
  });
}

describe("ProfileForm incremental edit submit (t058 A24, AC-001/AC-002)", () => {
  it("AC-001: changing only the timezone submits only the timezone field", async () => {
    const onSubmit = vi.fn(async () => undefined);
    renderForm({
      mode: "edit",
      initial: profile({ timezone: "Europe/London", locale: "en-US" }),
      onSubmit,
    });
    await screen.findByTestId("profile-form-name");

    changeTimezone("America/New_York");
    fireEvent.click(screen.getByTestId("profile-form-submit"));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    // The linked locale stays en-US for a non-Chinese timezone, so the
    // body holds exactly the one field the user changed — no stale
    // snapshot of the other fields another client may have edited.
    expect(onSubmit).toHaveBeenCalledWith({ timezone: "America/New_York" });
  });

  it("AC-001: a timezone change carries its linked locale change, nothing else", async () => {
    const onSubmit = vi.fn(async () => undefined);
    renderForm({
      mode: "edit",
      initial: profile({ timezone: "Europe/London", locale: "en-US" }),
      onSubmit,
    });
    await screen.findByTestId("profile-form-name");

    changeTimezone("Asia/Shanghai");
    fireEvent.click(screen.getByTestId("profile-form-submit"));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({
      timezone: "Asia/Shanghai",
      locale: "zh-CN",
    });
  });

  it("AC-002: toggling only capture_preview submits only capture_preview", async () => {
    const onSubmit = vi.fn(async () => undefined);
    renderForm({
      mode: "edit",
      initial: profile({ capture_preview: true }),
      onSubmit,
    });
    await screen.findByTestId("profile-form-name");

    fireEvent.click(
      screen.getByRole("checkbox", { name: en.formCapturePreview }),
    );
    fireEvent.click(screen.getByTestId("profile-form-submit"));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({ capture_preview: false });
  });

  it("submits an empty diff when nothing changed", async () => {
    const onSubmit = vi.fn(async () => undefined);
    renderForm({ mode: "edit", initial: profile(), onSubmit });
    await screen.findByTestId("profile-form-name");

    fireEvent.click(screen.getByTestId("profile-form-submit"));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith({});
  });

  it("create mode still submits the full values", async () => {
    const onSubmit = vi.fn(async () => undefined);
    renderForm({ mode: "create", onSubmit });
    await screen.findByTestId("profile-form-name");

    fireEvent.change(screen.getByTestId("profile-form-name"), {
      target: { value: "My env" },
    });
    fireEvent.click(screen.getByTestId("profile-form-submit"));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ name: "My env", screen_width: 1920 }),
    );
  });
});
