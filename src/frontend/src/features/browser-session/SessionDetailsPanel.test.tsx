import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { I18nProvider, en } from "../../i18n";
import type {
  FontSetInfo,
  GroupResponse,
  ProfileResponse,
  ProfileRuntimeResponse,
  ProxyResponse,
} from "../../shared/api/types";
import {
  SessionDetailsPanel,
  type SessionDetailsPanelProps,
} from "./SessionDetailsPanel";
import { SESS_COPY_VALUE, SESS_DETAILS_PANEL, SESS_DETAILS_TOGGLE } from "./session_keys";

function profile(overrides: Partial<ProfileResponse> = {}): ProfileResponse {
  return {
    id: "p1",
    name: "Alpha",
    display_number: 1,
    fingerprint_seed: 101,
    group_id: "g1",
    proxy_id: "px1",
    timezone: null,
    locale: null,
    screen_width: 1920,
    screen_height: 1080,
    include_cjk_fonts: false,
    humanize: false,
    human_preset: "default",
    geoip: true,
    clipboard_sync: true,
    auto_launch: false,
    color_scheme: "light",
    fingerprint_platform: "windows",
    font_set_id: "fs-1",
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
  overrides: Partial<ProfileRuntimeResponse> = {},
): ProfileRuntimeResponse {
  return {
    profile_id: "p1",
    display_number: 1,
    desired_state: "running",
    observed_state: "running",
    runtime_instance_id: "inst-1",
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    last_exit_event_id: null,
    last_started_at: "2026-01-01T10:00:00Z",
    last_coordinator_error: null,
    browser_product: "Chrome 131",
    browser_user_agent: "Mozilla/5.0 Test",
    font_set_id: "fs-1",
    missing_fonts: [],
    transport: {
      profile_id: "p1",
      browser_state: "running",
      stream_state: "running",
      transport_state: "ready",
      gateway_endpoint: "gateway.local:8080",
    },
    updated_at: "2026-01-01T10:00:00Z",
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

function proxy(overrides: Partial<ProxyResponse> = {}): ProxyResponse {
  const { proxy_url, observation_status, ...rest } = overrides;
  return {
    id: "px1",
    name: "US Proxy",
    scheme: "socks5",
    host: "1.2.3.4",
    port: 1080,
    username: null,
    has_password: false,
    credential_revision: 1,
    proxy_url: proxy_url ?? "socks5://1.2.3.4:1080",
    country_code: "US",
    observation_status: observation_status ?? "ok",
    region_label: "California",
    notes: null,
    used_by_count: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...rest,
  };
}

function fontSet(overrides: Partial<FontSetInfo> = {}): FontSetInfo {
  return {
    platform: "windows",
    set_id: "fs-1",
    integrity: { ok: true, file_count: 3 },
    file_count: 3,
    used_by_count: 1,
    state: "verified",
    revision: 1,
    verified_at: "2026-11-18T00:00:00+00:00",
    audited_at: null,
    ...overrides,
  };
}

function makeClipboard() {
  const writeText = vi.fn(async (_value: string) => undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  return writeText;
}

function renderPanel(overrides: Partial<SessionDetailsPanelProps> = {}) {
  const props: SessionDetailsPanelProps = {
    profile: profile(),
    runtime: runtime(),
    groups: [group()],
    proxies: [proxy()],
    fontSets: [fontSet()],
    open: true,
    ...overrides,
  };
  const view = render(
    <I18nProvider>
      <SessionDetailsPanel {...props} />
    </I18nProvider>,
  );
  return { ...view, props };
}

beforeEach(() => {
  localStorage.clear();
  makeClipboard();
});

describe("SessionDetailsPanel", () => {
  it("renders all four sections with localized values and without exposing raw internal IDs", () => {
    renderPanel();
    const panel = screen.getByTestId(SESS_DETAILS_PANEL);
    expect(panel.textContent).toContain(en.navEnvironments);
    expect(panel.textContent).toContain(en.envColNetwork);
    expect(panel.textContent).toContain(en.envColFingerprint);
    expect(panel.textContent).toContain(en.automationRuntimeState);

    expect(panel.textContent).toContain("Alpha");
    expect(panel.textContent).toContain("Work");
    expect(panel.textContent).toContain("US Proxy");
    expect(panel.textContent).toContain("1.2.3.4:1080");
    expect(panel.textContent).toContain("US");
    expect(panel.textContent).toContain("gateway.local:8080");
    expect(panel.textContent).toContain("Windows");
    expect(panel.textContent).toContain(en.fontSetWindowsCore);
    expect(panel.textContent).toContain(en.fontSetIntegrityOk);
    expect(panel.textContent).toContain("Chrome 131");
    expect(panel.textContent).toContain("Mozilla/5.0 Test");
    expect(panel.textContent).toContain(en.transportStateReady);
    expect(panel.textContent).not.toContain("ready");
    expect(panel.textContent).not.toContain("inst-1");
  });

  it.each([
    [null, "undefined"],
    ["half_open", "half_open"],
  ] as const)(
    "transport 原始值 %s 时详情 transport_state 回落本地化 unknown（AC-004）",
    (rawState, leakedRaw) => {
      renderPanel({
        runtime: runtime({
          transport:
            rawState === null
              ? null
              : {
                  profile_id: "p1",
                  browser_state: "running",
                  stream_state: "running",
                  transport_state: rawState as never,
                },
        }),
      });
      const panel = screen.getByTestId(SESS_DETAILS_PANEL);
      expect(panel.textContent).toContain(en.transportStateUnknown);
      expect(panel.textContent).not.toContain(leakedRaw);
    },
  );

  it("renders nothing at all when closed (AC-001)", () => {
    renderPanel({ open: false });
    expect(screen.queryByTestId(SESS_DETAILS_PANEL)).toBeNull();
    expect(screen.queryAllByTestId(SESS_COPY_VALUE)).toHaveLength(0);
  });

  it("carries no internal title or second toggle (AC-001)", () => {
    renderPanel({ open: true });
    expect(screen.queryByTestId(SESS_DETAILS_TOGGLE)).toBeNull();
    expect(screen.queryByText(en.sessDetails)).toBeNull();
  });

  it("shows detecting region while the proxy observation is pending", () => {
    renderPanel({
      proxies: [
        proxy({ observation_status: "pending", country_code: null }),
      ],
    });
    const panel = screen.getByTestId(SESS_DETAILS_PANEL);
    expect(panel.textContent).toContain(en.proxyCountryProbing);
    expect(panel.textContent).not.toContain(en.proxyCountryUnknown);
  });
});
