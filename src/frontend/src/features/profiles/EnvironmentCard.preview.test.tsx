import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { I18nProvider } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ToastProvider } from "../../shared/ui";
import type {
  ProfileResponse,
  ProfileRuntimeResponse,
} from "../../shared/api/types";
import { EnvironmentCard } from "./EnvironmentCard";
import type { EnvironmentRow } from "./EnvironmentTable";

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => undefined;
  }
  if (!HTMLElement.prototype.hasPointerCapture) {
    HTMLElement.prototype.hasPointerCapture = () => false;
  }
  if (!HTMLElement.prototype.releasePointerCapture) {
    HTMLElement.prototype.releasePointerCapture = () => undefined;
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
    last_started_at: null,
    last_stopped_at: null,
    last_coordinator_error: null,
    preview_captured_at: null,
    updated_at: "2026-01-01T10:00:00Z",
  };
}

let queryClient: QueryClient;

beforeEach(() => {
  localStorage.clear();
  queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
});

function tree(previewCapturedAt: string | null | undefined): ReactElement {
  const row: EnvironmentRow = {
    profile: profile({ id: "p1", name: "Alpha" }),
    runtime: runtime("p1", "running"),
  };
  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <EnvironmentCard
              row={row}
              selected={false}
              onToggle={vi.fn()}
              onAction={vi.fn()}
              previewCapturedAt={previewCapturedAt}
            />
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>
  );
}

describe("EnvironmentCard preview thumbnail", () => {
  it("renders a versioned img when preview_captured_at is present", () => {
    const capturedAt = "2026-01-01T00:00:05Z";
    render(tree(capturedAt));

    const img = screen.getByTestId("env-card-preview-img-p1");
    expect(img.tagName).toBe("IMG");
    expect(img.getAttribute("src")).toBe(
      `/api/v1/profiles/p1/preview?v=${encodeURIComponent(capturedAt)}`,
    );
    expect(img.getAttribute("loading")).toBe("lazy");
    expect(img.className).toContain("object-cover");
  });

  it("renders the placeholder and no img when the value is null", () => {
    render(tree(null));

    const placeholder = screen.getByTestId("env-card-preview-p1");
    expect(placeholder.textContent).toBe("");
    expect(screen.queryByTestId("env-card-preview-img-p1")).toBeNull();
    expect(placeholder.querySelector("img")).toBeNull();
  });

  it("renders the placeholder and no img when the prop is omitted", () => {
    render(tree(undefined));

    const placeholder = screen.getByTestId("env-card-preview-p1");
    expect(placeholder.textContent).toBe("");
    expect(placeholder.querySelector("img")).toBeNull();
  });

  it("falls back to the placeholder when the img fails to load", () => {
    render(tree("2026-01-01T00:00:05Z"));

    fireEvent.error(screen.getByTestId("env-card-preview-img-p1"));
    expect(screen.queryByTestId("env-card-preview-img-p1")).toBeNull();
    const placeholder = screen.getByTestId("env-card-preview-p1");
    expect(placeholder.textContent).toBe("");
    expect(placeholder.querySelector("img")).toBeNull();
  });

  it("re-attempts the image with a new URL when a new captured_at arrives", () => {
    const capturedAt2 = "2026-01-01T00:00:09Z";
    const view = render(tree("2026-01-01T00:00:05Z"));

    fireEvent.error(screen.getByTestId("env-card-preview-img-p1"));
    expect(screen.queryByTestId("env-card-preview-img-p1")).toBeNull();

    view.rerender(tree(capturedAt2));
    const img = screen.getByTestId("env-card-preview-img-p1");
    expect(img.getAttribute("src")).toBe(
      `/api/v1/profiles/p1/preview?v=${encodeURIComponent(capturedAt2)}`,
    );
  });
});
