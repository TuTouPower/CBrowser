import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
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
    gpu_family: "auto",
    humanize: false,
    human_preset: "default",
    geoip: true,
    clipboard_sync: true,
    auto_launch: false,
    color_scheme: null,
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

let writeText: ReturnType<typeof makeClipboard>;

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
  writeText = makeClipboard();
});

describe("SessionDetailsPanel", () => {
  it("renders all four sections with values joined from props", () => {
    renderPanel();
    const panel = screen.getByTestId(SESS_DETAILS_PANEL);
    expect(panel.textContent).toContain(en.navEnvironments);
    expect(panel.textContent).toContain(en.envColNetwork);
    expect(panel.textContent).toContain(en.envColFingerprint);
    expect(panel.textContent).toContain(en.automationRuntimeState);

    expect(panel.textContent).toContain("Alpha");
    expect(panel.textContent).toContain("p1");
    expect(panel.textContent).toContain("Work");
    expect(panel.textContent).toContain("US Proxy");
    expect(panel.textContent).toContain("socks5");
    expect(panel.textContent).toContain("1.2.3.4:1080");
    expect(panel.textContent).toContain("US");
    expect(panel.textContent).toContain("gateway.local:8080");
    expect(panel.textContent).toContain("windows");
    expect(panel.textContent).toContain("fs-1");
    expect(panel.textContent).toContain(en.fontSetIntegrityOk);
    expect(panel.textContent).toContain("Chrome 131");
    expect(panel.textContent).toContain("Mozilla/5.0 Test");
    expect(panel.textContent).toContain("inst-1");
    // t061 AC-004: transport_state renders its localized label, never
    // the raw machine value.
    expect(panel.textContent).toContain(en.transportStateReady);
    expect(panel.textContent).not.toContain("ready");
    expect(panel.textContent).toContain("2026-01-01T10:00:00Z");
  });

  // t061 replacement note: the pre-t061 test "keeps the container but
  // hides content when closed" asserted the closed panel still occupies
  // its fixed-width container. AC-001 replaces that contract: the top
  // header button is the only toggle and a closed panel renders
  // nothing, so it occupies no width.
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
    // test f003: pending (detecting) must not read as unknown.
    renderPanel({
      proxies: [
        proxy({ observation_status: "pending", country_code: null }),
      ],
    });
    const panel = screen.getByTestId(SESS_DETAILS_PANEL);
    expect(panel.textContent).toContain(en.proxyCountryProbing);
    expect(panel.textContent).not.toContain(en.proxyCountryUnknown);
  });

  it("copies each value through the clipboard and confirms", async () => {
    renderPanel();
    const buttons = screen.getAllByTestId(SESS_COPY_VALUE);
    expect(buttons.length).toBeGreaterThan(1);
    for (const button of buttons) {
      const row = button.closest("dd");
      const shown = row?.textContent
        ?.replace(button.textContent ?? "", "")
        .trim();
      expect(shown).toBeTruthy();
      writeText.mockClear();
      fireEvent.click(button);
      expect(writeText).toHaveBeenCalledWith(shown);
    }
    expect(await screen.findByText(en.sessCopied)).toBeInTheDocument();
  });

  it("shows the last coordinator error when present", () => {
    renderPanel({
      runtime: runtime({ last_coordinator_error: "Supervisor unreachable" }),
    });
    expect(screen.getByText("Supervisor unreachable")).toBeInTheDocument();
  });

  it("warns about missing fonts and copies the value", async () => {
    renderPanel({ runtime: runtime({ missing_fonts: ["Arial", "SimSun"] }) });
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Arial");
    expect(alert.textContent).toContain("SimSun");
    const copy = within(alert).getByTestId(SESS_COPY_VALUE);
    fireEvent.click(copy);
    expect(writeText).toHaveBeenCalledWith("Arial, SimSun");
  });

  it("labels missing detection fonts as uncovered, not as integrity damage", () => {
    renderPanel({ runtime: runtime({ missing_fonts: ["Arial", "SimSun"] }) });
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain(en.fontSetDetectionMissing);
    expect(alert.textContent).not.toContain(en.fontSetIntegrityBad);
  });

  it("renders without crashing when runtime and joins are empty", () => {
    renderPanel({
      runtime: null,
      groups: [],
      proxies: [],
      fontSets: [],
      profile: profile({ group_id: null, proxy_id: null, font_set_id: null }),
    });
    const panel = screen.getByTestId(SESS_DETAILS_PANEL);
    expect(panel.textContent).toContain(en.navEnvironments);
    expect(panel.textContent).toContain(en.envColNetwork);
    expect(panel.textContent).toContain(en.envColFingerprint);
    expect(panel.textContent).toContain(en.automationRuntimeState);
    expect(panel.textContent).toContain(en.envDirect);
    expect(panel.textContent).toContain(en.sessUngrouped);
    expect(screen.getAllByTestId(SESS_COPY_VALUE).length).toBeGreaterThan(0);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("marks pending configuration when config versions differ", () => {
    renderPanel({
      runtime: runtime({ config_version: 2 }),
      profile: profile({ current_config_version: 3 }),
    });
    expect(screen.getByTestId(SESS_DETAILS_PANEL).textContent).toContain(
      en.sessApplyPending,
    );
  });

  it("does not crash when the clipboard API is unavailable", () => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: undefined,
    });
    renderPanel();
    fireEvent.click(screen.getAllByTestId(SESS_COPY_VALUE)[0]!);
    expect(screen.getByTestId(SESS_DETAILS_PANEL)).toBeInTheDocument();
  });
});
