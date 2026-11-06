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

function fontSet(overrides: Partial<FontSetInfo> = {}): FontSetInfo {
  return {
    platform: "windows",
    set_id: "fs-1",
    source: "t044",
    source_version: "v1",
    created_at: "2026-01-01T00:00:00Z",
    integrity: {
      ok: true,
      problems: [],
      missing_fonts: [],
      hash_mismatches: [],
      unregistered_fonts: [],
      file_count: 10,
      detection: {},
    },
    file_count: 10,
    used_by_count: 0,
    ...overrides,
  };
}

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
    country_code: "US",
    region_label: null,
    notes: null,
    used_by_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function profile(): ProfileResponse {
  return {
    id: "p1",
    name: "Original",
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
  };
}

function makeStub(opts: {
  fontSets?: FontSetInfo[];
  groups?: GroupResponse[];
  proxies?: ProxyResponse[];
} = {}) {
  return {
    groups: {
      list: vi.fn(async () => opts.groups ?? []),
      create: vi.fn(async (data: { name: string }) => ({ ...group(), ...data })),
    },
    proxies: { list: vi.fn(async () => opts.proxies ?? []) },
    fontSets: { list: vi.fn(async () => opts.fontSets ?? []) },
  } as unknown as ApiClient;
}

function renderForm(opts: {
  mode: "create" | "edit";
  initial?: ProfileResponse;
  onSubmit?: (
    values: ProfileCreateRequest | ProfileUpdateRequest,
  ) => Promise<void>;
  submitLabel?: string;
  onDirtyRuntimeConfig?: (changed: boolean) => void;
  stub: ApiClient;
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={opts.stub}>
              <MemoryRouter>
                <ProfileForm
                  mode={opts.mode}
                  initial={opts.initial}
                  onSubmit={opts.onSubmit ?? (async () => undefined)}
                  submitLabel={opts.submitLabel}
                  onDirtyRuntimeConfig={opts.onDirtyRuntimeConfig}
                />
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("ProfileForm", () => {
  it("renders the four sections, blocks an empty name and submits", async () => {
    const onSubmit = vi.fn(async () => undefined);
    renderForm({
      mode: "create",
      stub: makeStub({ proxies: [proxy()], groups: [group()] }),
      onSubmit,
    });

    expect(screen.getByText(en.formSectionBasic)).toBeInTheDocument();
    expect(screen.getByText(en.formSectionNetwork)).toBeInTheDocument();
    expect(screen.getByText(en.formSectionFingerprint)).toBeInTheDocument();
    expect(screen.getByText(en.formSectionAdvanced)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("profile-form-submit"));
    expect(await screen.findByTestId("profile-form-error")).toBeInTheDocument();
    expect(screen.getByTestId("profile-form-name-error")).toHaveTextContent(
      en.formNameRequired,
    );
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.change(screen.getByTestId("profile-form-name"), {
      target: { value: "My env" },
    });
    fireEvent.click(screen.getByTestId("profile-form-submit"));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ name: "My env" }),
    );
  });

  it("filters font sets by platform and defaults to the newest", async () => {
    const winOld = fontSet({
      set_id: "win-old",
      platform: "windows",
      created_at: "2026-01-01T00:00:00Z",
      source_version: "v1",
    });
    const winNew = fontSet({
      set_id: "win-new",
      platform: "windows",
      created_at: "2026-06-01T00:00:00Z",
      source_version: "v2",
    });
    const mac = fontSet({
      set_id: "mac-1",
      platform: "macos",
      created_at: "2026-12-01T00:00:00Z",
      source_version: "v9",
    });
    renderForm({
      mode: "create",
      stub: makeStub({ fontSets: [winOld, winNew, mac] }),
    });

    const list = await screen.findByTestId("profile-form-fontset-list");
    await waitFor(() => expect(list.textContent).toContain("win-old"));
    expect(list.textContent).toContain("win-new");
    expect(list.textContent).not.toContain("mac-1");

    await waitFor(() =>
      expect(
        screen.getByTestId("profile-form-fontset-selected").textContent,
      ).toBe("win-new"),
    );
    expect(screen.getByTestId("profile-form-fontset-meta").textContent).toContain(
      "v2",
    );
    expect(screen.getByTestId("profile-form-fontset-meta").textContent).toContain(
      en.fontSetIntegrityOk,
    );
  });

  it("warns when the selected font set fails its integrity check", async () => {
    const bad = fontSet({
      set_id: "bad",
      platform: "windows",
      created_at: "2026-01-01T00:00:00Z",
      integrity: {
        ...fontSet().integrity,
        ok: false,
        problems: ["hash mismatch"],
      },
    });
    renderForm({ mode: "create", stub: makeStub({ fontSets: [bad] }) });

    const warning = await screen.findByTestId("profile-form-fontset-warning");
    expect(warning.textContent).toContain(en.formFontSetInconsistent);
  });

  it("reseeds the fingerprint seed", async () => {
    renderForm({ mode: "create", stub: makeStub() });
    const before = screen.getByTestId("profile-form-seed").textContent;
    fireEvent.click(screen.getByTestId("profile-form-reseed"));
    await waitFor(() =>
      expect(screen.getByTestId("profile-form-seed").textContent).not.toBe(
        before,
      ),
    );
  });

  it("does not report a runtime-config change for metadata-only edits", async () => {
    const onDirtyRuntimeConfig = vi.fn();
    renderForm({
      mode: "edit",
      initial: profile(),
      onDirtyRuntimeConfig,
      stub: makeStub(),
    });

    fireEvent.change(screen.getByTestId("profile-form-notes"), {
      target: { value: "a note" },
    });
    await waitFor(() => expect(onDirtyRuntimeConfig).toHaveBeenCalled());
    expect(onDirtyRuntimeConfig).not.toHaveBeenCalledWith(true);
  });

  it("reports a runtime-config change when a runtime field changes", async () => {
    const onDirtyRuntimeConfig = vi.fn();
    renderForm({
      mode: "edit",
      initial: profile(),
      onDirtyRuntimeConfig,
      stub: makeStub(),
    });

    fireEvent.change(screen.getByTestId("profile-form-timezone"), {
      target: { value: "Asia/Shanghai" },
    });
    await waitFor(() =>
      expect(onDirtyRuntimeConfig).toHaveBeenCalledWith(true),
    );
  });

  it("submits the full values in edit mode", async () => {
    const onSubmit = vi.fn(async () => undefined);
    renderForm({
      mode: "edit",
      initial: profile(),
      onSubmit,
      stub: makeStub(),
    });

    fireEvent.click(screen.getByTestId("profile-form-submit"));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Original",
        screen_width: 1920,
        geoip: true,
      }),
    );
  });
});
