import { beforeAll, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider, en } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ToastProvider } from "../../shared/ui";
import { ApiClientContext } from "../../shared/api/client_context";
import type { ApiClient } from "../../shared/api/client";
import type {
  ProfileCreateRequest,
  ProfileResponse,
  ProfileRuntimeResponse,
} from "../../shared/api/types";
import { ProfileCreateDialog } from "./ProfileCreateDialog";

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

function runtime(): ProfileRuntimeResponse {
  return {
    profile_id: "p-new",
    desired_state: "running",
    observed_state: "running",
    runtime_instance_id: "inst_1",
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    last_exit_event_id: null,
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function makeStub() {
  return {
    profiles: {
      create: vi.fn(async (data: ProfileCreateRequest) => ({
        ...profile(),
        id: "p-new",
        ...data,
      })),
      setDesiredState: vi.fn(async () => runtime()),
      list: vi.fn(async () => [profile()]),
      get: vi.fn(async () => profile()),
      getRuntime: vi.fn(async () => runtime()),
      update: vi.fn(async () => profile()),
      stop: vi.fn(async () => runtime()),
      retrySearchDefaults: vi.fn(async () => runtime()),
      delete: vi.fn(async () => undefined),
      duplicate: vi.fn(async () => profile()),
      reset: vi.fn(async () => profile()),
    },
    groups: {
      list: vi.fn(async () => []),
      create: vi.fn(async () => ({
        id: "g1",
        name: "Work",
        color: "slate",
        sort_order: 0,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      })),
    },
    proxies: { list: vi.fn(async () => []) },
    fontSets: { list: vi.fn(async () => []) },
  } as unknown as ApiClient & {
    profiles: {
      create: ReturnType<typeof vi.fn>;
      setDesiredState: ReturnType<typeof vi.fn>;
    };
  };
}

function renderDialog(
  stub: ReturnType<typeof makeStub>,
  onOpenChange: (open: boolean) => void,
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={stub}>
              <MemoryRouter>
                <ProfileCreateDialog open onOpenChange={onOpenChange} />
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("ProfileCreateDialog", () => {
  it("creates a profile from the form", async () => {
    const stub = makeStub();
    const onOpenChange = vi.fn();
    renderDialog(stub, onOpenChange);

    await screen.findByTestId("env-new-dialog");
    fireEvent.change(screen.getByTestId("profile-form-name"), {
      target: { value: "New env" },
    });
    fireEvent.click(screen.getByTestId("profile-form-submit"));

    await waitFor(() => expect(stub.profiles.create).toHaveBeenCalledTimes(1));
    expect(stub.profiles.create).toHaveBeenCalledWith(
      expect.objectContaining({ name: "New env" }),
      expect.any(String),
    );
    expect(stub.profiles.setDesiredState).not.toHaveBeenCalled();
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("starts the profile after create-and-start", async () => {
    const stub = makeStub();
    const onOpenChange = vi.fn();
    renderDialog(stub, onOpenChange);

    await screen.findByTestId("env-new-dialog");
    fireEvent.change(screen.getByTestId("profile-form-name"), {
      target: { value: "Started env" },
    });
    fireEvent.click(screen.getByTestId("profile-form-submit-start"));

    await waitFor(() =>
      expect(stub.profiles.setDesiredState).toHaveBeenCalledTimes(1),
    );
    expect(stub.profiles.setDesiredState).toHaveBeenCalledWith(
      "p-new",
      "running",
      expect.any(String),
    );
    const createOrder = stub.profiles.create.mock.invocationCallOrder[0] as number;
    const startOrder = stub.profiles.setDesiredState.mock
      .invocationCallOrder[0] as number;
    expect(createOrder).toBeLessThan(startOrder);
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("blocks submission when the name is empty and shows a field error", async () => {
    const stub = makeStub();
    const onOpenChange = vi.fn();
    renderDialog(stub, onOpenChange);

    await screen.findByTestId("env-new-dialog");
    const dialog = screen.getByTestId("env-new-dialog");
    fireEvent.click(within(dialog).getByTestId("profile-form-submit"));

    expect(await within(dialog).findByTestId("profile-form-error")).toBeInTheDocument();
    expect(within(dialog).getByTestId("profile-form-name-error")).toHaveTextContent(
      en.formNameRequired,
    );
    expect(stub.profiles.create).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});
