import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider, en, zh } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ToastProvider } from "../../shared/ui";
import { type ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import type {
  GroupResponse,
  ProfileResponse,
  ProfileRuntimeResponse,
} from "../../shared/api/types";
import { SessionHeader, type SessionHeaderProps } from "./SessionHeader";
import {
  SESS_APPLY_RESTART,
  SESS_AUDIO_TOGGLE,
  SESS_DIAG_TOGGLE,
  SESS_DETAILS_TOGGLE,
  SESS_HEADER,
  SESS_STOP,
} from "./session_keys";

const OBSERVED_STATE_ID = "sess-observed-state";
const TRANSPORT_STATE_ID = "sess-transport-state";
const APPLY_PENDING_ID = "sess-apply-pending";
const FOCUS_TOGGLE_ID = "sess-focus-toggle";

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
    last_started_at: null,
    last_stopped_at: null,
    last_coordinator_error: null,
    transport: {
      profile_id: profileId,
      browser_state: "running",
      stream_state: "running",
      transport_state: "ready",
    },
    updated_at: "2026-01-01T10:00:00Z",
    ...overrides,
  };
}

function makeStub(runtimeData: ProfileRuntimeResponse): ApiClient {
  return {
    profiles: {
      getRuntime: vi.fn(async () => runtimeData),
    },
  } as unknown as ApiClient;
}

function renderHeader(
  props: SessionHeaderProps,
  switcherRuntime?: ProfileRuntimeResponse,
) {
  const client = makeStub(
    switcherRuntime ?? props.runtime ?? runtime(props.profile.id, "stopped"),
  );
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
                <SessionHeader {...props} />
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

function fixture(
  overrides: Partial<SessionHeaderProps> = {},
): SessionHeaderProps {
  return {
    profile: profile(),
    runtime: runtime("p1", "running"),
    profiles: [profile()],
    groups: [group()],
    audioMuted: false,
    diagnosticsOpen: false,
    detailsOpen: false,
    focusMode: false,
    onAudioToggle: vi.fn(),
    onDiagnosticsToggle: vi.fn(),
    onDetailsToggle: vi.fn(),
    onFocusToggle: vi.fn(),
    onStop: vi.fn(),
    onApplyRestart: vi.fn(),
    ...overrides,
  };
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("cbrowser.locale", "en");
});

describe("SessionHeader", () => {
  it("显示 observed state 与 transport 文案，状态以文字呈现", () => {
    renderHeader(fixture());

    const header = screen.getByTestId(SESS_HEADER);
    expect(within(header).getByText(en.sessObservedState)).toBeInTheDocument();
    expect(
      within(screen.getByTestId(OBSERVED_STATE_ID)).getByText(en.sessRunning),
    ).toBeInTheDocument();
    expect(within(header).getByText(en.sessTransport)).toBeInTheDocument();
    expect(
      within(screen.getByTestId(TRANSPORT_STATE_ID)).getByText(
        en.transportStateReady,
      ),
    ).toBeInTheDocument();
  });

  // t061 AC-004: the badge renders the localized label for each
  // transport state, never the raw machine value (the pre-t061 suite
  // asserted the raw values verbatim).
  it.each([
    ["ready", en.transportStateReady],
    ["recovering", en.transportStateRecovering],
    ["failed", en.transportStateFailed],
    ["unknown", en.transportStateUnknown],
  ] as const)("transport 状态 %s 显示本地化文案", (transportState, label) => {
    const props = fixture({
      runtime: runtime("p1", "running", {
        transport: {
          profile_id: "p1",
          browser_state: "running",
          stream_state: "running",
          transport_state: transportState,
        },
      }),
    });
    renderHeader(props);

    expect(
      within(screen.getByTestId(TRANSPORT_STATE_ID)).getByText(label),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId(TRANSPORT_STATE_ID)).queryByText(
        transportState,
      ),
    ).toBeNull();
  });

  it("中文界面下 transport 显示中文文案（AC-004）", () => {
    localStorage.setItem("cbrowser.locale", "zh");
    renderHeader(fixture());

    expect(
      within(screen.getByTestId(TRANSPORT_STATE_ID)).getByText(
        zh.transportStateReady,
      ),
    ).toBeInTheDocument();
    expect(zh.transportStateReady).toBe("正常");
  });

  it("未知或缺失的 transport 值回落本地化 unknown，不泄漏原始机器码", () => {
    const props = fixture({
      runtime: runtime("p1", "running", {
        transport: {
          profile_id: "p1",
          browser_state: "running",
          stream_state: "running",
          transport_state: "half_open" as never,
        },
      }),
    });
    renderHeader(props);

    const badge = screen.getByTestId(TRANSPORT_STATE_ID);
    expect(within(badge).getByText(en.transportStateUnknown)).toBeInTheDocument();
    expect(within(badge).queryByText("half_open")).toBeNull();
  });

  it("runtime 为空时 observed 回落 stopped、transport 回落 unknown，无待应用标记", () => {
    renderHeader(fixture({ runtime: null }));

    expect(
      within(screen.getByTestId(OBSERVED_STATE_ID)).getByText(en.sessStopped),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId(TRANSPORT_STATE_ID)).getByText(
        en.transportStateUnknown,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByTestId(APPLY_PENDING_ID)).toBeNull();
  });

  it("config_version 与 current_config_version 相等时不显示待应用标记", () => {
    renderHeader(
      fixture({ runtime: runtime("p1", "running", { config_version: 1 }) }),
    );

    expect(screen.queryByTestId(APPLY_PENDING_ID)).toBeNull();
    expect(screen.queryByText(en.sessApplyPending)).toBeNull();
    expect(screen.queryByTestId(SESS_APPLY_RESTART)).toBeNull();
  });

  it("config_version 不等时显示待应用标记，点击应用并重启调用 onApplyRestart", () => {
    const props = fixture({
      runtime: runtime("p1", "running", { config_version: 2 }),
    });
    renderHeader(props);

    expect(screen.getByTestId(APPLY_PENDING_ID)).toHaveTextContent(
      en.sessApplyPending,
    );
    fireEvent.click(screen.getByTestId(SESS_APPLY_RESTART));
    expect(props.onApplyRestart).toHaveBeenCalledTimes(1);
  });

  it("各按钮点击调用对应回调", () => {
    const props = fixture();
    renderHeader(props);

    fireEvent.click(screen.getByTestId(SESS_AUDIO_TOGGLE));
    fireEvent.click(screen.getByTestId(SESS_DIAG_TOGGLE));
    fireEvent.click(screen.getByTestId(SESS_DETAILS_TOGGLE));
    fireEvent.click(screen.getByTestId(FOCUS_TOGGLE_ID));
    fireEvent.click(screen.getByTestId(SESS_STOP));

    expect(props.onAudioToggle).toHaveBeenCalledTimes(1);
    expect(props.onDiagnosticsToggle).toHaveBeenCalledTimes(1);
    expect(props.onDetailsToggle).toHaveBeenCalledTimes(1);
    expect(props.onFocusToggle).toHaveBeenCalledTimes(1);
    expect(props.onStop).toHaveBeenCalledTimes(1);
  });

  it("图标按钮带 label 与 aria-pressed 状态", () => {
    renderHeader(
      fixture({
        audioMuted: true,
        diagnosticsOpen: true,
        detailsOpen: true,
        focusMode: true,
      }),
    );

    expect(screen.getByTestId(SESS_AUDIO_TOGGLE)).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByTestId(SESS_AUDIO_TOGGLE)).toHaveAttribute(
      "aria-label",
      en.audioUnmute,
    );
    expect(screen.getByTestId(SESS_DIAG_TOGGLE)).toHaveAttribute(
      "aria-label",
      en.sessionHideDiagnostics,
    );
    expect(screen.getByTestId(SESS_DETAILS_TOGGLE)).toHaveAttribute(
      "aria-label",
      en.sessDetailsClose,
    );
    expect(screen.getByTestId(FOCUS_TOGGLE_ID)).toHaveAttribute(
      "aria-label",
      en.sessFocus,
    );
    expect(screen.getByTestId(SESS_STOP)).toHaveAttribute(
      "aria-label",
      en.sessStop,
    );
  });

  it("页头不使用 primary 按钮", () => {
    renderHeader(
      fixture({ runtime: runtime("p1", "running", { config_version: 2 }) }),
    );

    const primaryButtons = within(screen.getByTestId(SESS_HEADER))
      .getAllByRole("button")
      .filter((button) => button.classList.contains("bg-accent"));
    expect(primaryButtons).toHaveLength(0);
  });

  it("Escape 与转发远端的组合键不触发页头回调", () => {
    const props = fixture();
    renderHeader(props);

    fireEvent.keyDown(screen.getByTestId(SESS_HEADER), { key: "Escape" });
    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.keyDown(document, { key: "c", ctrlKey: true });
    fireEvent.keyDown(document, { key: "Tab" });

    for (const callback of [
      props.onAudioToggle,
      props.onDiagnosticsToggle,
      props.onDetailsToggle,
      props.onFocusToggle,
      props.onStop,
      props.onApplyRestart,
    ]) {
      expect(callback).not.toHaveBeenCalled();
    }
  });

  it("isPending 时 Stop 与 Apply 并重启禁用", () => {
    renderHeader(
      fixture({
        runtime: runtime("p1", "running", { config_version: 2 }),
        isPending: true,
      }),
    );

    expect(screen.getByTestId(SESS_STOP)).toBeDisabled();
    expect(screen.getByTestId(SESS_APPLY_RESTART)).toBeDisabled();
  });

  it("apply error 由 SessionPage 渲染（Header 只负责 pending 禁用）", () => {
    // Header 本身不渲染 apply error，该断言锁定 Header 不越权；
    // 真正的 apply error Banner 由 SessionPage.test 覆盖。
    renderHeader(
      fixture({
        runtime: runtime("p1", "running", { config_version: 2 }),
        isPending: false,
      }),
    );
    expect(screen.getByTestId(SESS_APPLY_RESTART)).not.toBeDisabled();
  });
});
