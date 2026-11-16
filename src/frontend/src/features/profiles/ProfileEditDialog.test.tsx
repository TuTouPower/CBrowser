import { beforeAll, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ToastProvider } from "../../shared/ui";
import { ApiClientContext } from "../../shared/api/client_context";
import type { ApiClient } from "../../shared/api/client";
import type { ProfileResponse } from "../../shared/api/types";
import { ProfileEditDialog } from "./ProfileEditDialog";

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
  if (!HTMLElement.prototype.hasPointerCapture) {
    HTMLElement.prototype.hasPointerCapture = () => false;
  }
  if (!HTMLElement.prototype.releasePointerCapture) {
    HTMLElement.prototype.releasePointerCapture = () => undefined;
  }
});

function profile(): ProfileResponse {
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
  };
}

function makeStub(updateImpl?: (id: string, data: unknown) => Promise<ProfileResponse>) {
  return {
    profiles: {
      update: vi.fn(
        updateImpl ?? (async () => profile()),
      ),
      list: vi.fn(async () => [profile()]),
      get: vi.fn(async () => profile()),
      getRuntime: vi.fn(async () => undefined),
    },
    groups: { list: vi.fn(async () => []) },
    proxies: { list: vi.fn(async () => []) },
    fontSets: {
      list: vi.fn(async () => ({
        items: [],
        default_font_set_id: { windows: null, macos: null },
      })),
    },
  } as unknown as ApiClient & {
    profiles: { update: ReturnType<typeof vi.fn> };
  };
}

function renderDialog(
  stub: ReturnType<typeof makeStub>,
  onOpenChange: (open: boolean) => void,
) {
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
            <ApiClientContext.Provider value={stub}>
              <MemoryRouter>
                <ProfileEditDialog
                  open
                  profile={profile()}
                  onOpenChange={onOpenChange}
                />
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

// t073 AC-006: 宽编辑弹窗、差分更新、失败不关窗。
describe("ProfileEditDialog", () => {
  it("uses the wide lg dialog container", async () => {
    renderDialog(makeStub(), vi.fn());
    const dialog = await screen.findByRole("dialog");
    expect(dialog.className).toContain("max-w-dialog-lg");
    expect(dialog.className).toContain("max-h-dialog-height");
    expect(screen.getByTestId("env-edit-dialog")).toBeInTheDocument();
  });

  it("submits only changed fields and closes on success", async () => {
    const stub = makeStub();
    const onOpenChange = vi.fn();
    renderDialog(stub, onOpenChange);

    const dialog = await screen.findByTestId("env-edit-dialog");
    fireEvent.change(within(dialog).getByTestId("profile-form-name"), {
      target: { value: "Renamed" },
    });
    fireEvent.click(within(dialog).getByTestId("profile-form-submit"));

    await waitFor(() => expect(stub.profiles.update).toHaveBeenCalledTimes(1));
    const [id, data] = stub.profiles.update.mock.calls[0] as [
      string,
      Record<string, unknown>,
      string,
    ];
    expect(id).toBe("p1");
    expect(data).toEqual({ name: "Renamed" });
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("keeps the dialog open and shows an error when update fails", async () => {
    const stub = makeStub(async () => {
      throw new Error("boom");
    });
    const onOpenChange = vi.fn();
    renderDialog(stub, onOpenChange);

    const dialog = await screen.findByTestId("env-edit-dialog");
    fireEvent.change(within(dialog).getByTestId("profile-form-name"), {
      target: { value: "Renamed" },
    });
    fireEvent.click(within(dialog).getByTestId("profile-form-submit"));

    expect(await screen.findByTestId("env-edit-error")).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);

    // t073_gen_f001: 关闭回调必须重置 saveError，避免关闭后重开残留旧错误横幅。
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByTestId("env-edit-error")).toBeNull(),
    );
  });
});
