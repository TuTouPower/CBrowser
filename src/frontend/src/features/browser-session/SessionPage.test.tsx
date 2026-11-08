import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider, en, zh } from "../../i18n";
import { ThemeProvider } from "../../theme";
import { ToastProvider } from "../../shared/ui";
import { ApiError, type ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import type {
  FontSetInfo,
  GroupResponse,
  ProfileResponse,
  ProfileRuntimeResponse,
  ProxyResponse,
} from "../../shared/api/types";
import type { SessionDiagnosticsData, SessionStage } from "./types";
import {
  SESS_PAGE,
  SESS_HEADER,
  SESS_IFRAME,
  SESS_STAGE,
  SESS_STAGE_PANEL,
  SESS_DETAILS_PANEL,
  SESS_DETAILS_TOGGLE,
  SESS_FOCUS_TOOLBAR,
  SESS_FOCUS_EXIT,
  SESS_APPLY_RESTART,
  SESS_STOP,
  SESS_AUDIO_TOGGLE,
  SESS_DIAG_TOGGLE,
  sessId,
} from "./session_keys";
import { SessionPage } from "./SessionPage";
import { SessionFocusProvider } from "./session_focus";

const hookState = vi.hoisted(() => ({
  stage: "connected" as SessionStage,
  diagnostics: {
    stage: "connected",
    profileId: "p1",
    connectionState: "connected",
    framesDecoded: 128,
  } as SessionDiagnosticsData,
  errorMessage: null as string | null,
  reloadKey: 0,
  audioMuted: false,
  reconnect: vi.fn(),
  toggleAudio: vi.fn(),
}));

vi.mock("./useBrowserSession", () => ({
  useBrowserSession: () => ({
    stage: hookState.stage,
    diagnostics: hookState.diagnostics,
    errorMessage: hookState.errorMessage,
    reloadKey: hookState.reloadKey,
    reconnect: hookState.reconnect,
    audioMuted: hookState.audioMuted,
    toggleAudio: hookState.toggleAudio,
  }),
}));

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
  if (!window.ResizeObserver) {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
  }
  if (!window.matchMedia) {
    vi.stubGlobal("matchMedia", () => ({
      matches: false,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
    }));
  }
});

function profile(overrides: Partial<ProfileResponse> = {}): ProfileResponse {
  return {
    id: "p1",
    name: "Profile One",
    group_id: null,
    proxy_id: null,
    timezone: "UTC",
    locale: "en-US",
    fingerprint_platform: "windows",
    font_set_id: null,
    clipboard_sync: true,
    current_config_version: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  } as ProfileResponse;
}

function runtime(
  profileId: string,
  observed: ProfileRuntimeResponse["observed_state"],
  overrides: Partial<ProfileRuntimeResponse> = {}): ProfileRuntimeResponse {
  return {
    profile_id: profileId,
    observed_state: observed,
    desired_state: observed === "running" ? "running" : "stopped",
    runtime_instance_id: "inst-1",
    config_version: 1,
    last_started_at: "2026-01-01T00:00:00Z",
    last_stopped_at: null,
    browser_product: "Chrome/146",
    browser_user_agent: "Mozilla/5.0",
    font_set_id: null,
    missing_fonts: [],
    last_coordinator_error: null,
    transport: null,
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  } as ProfileRuntimeResponse;
}

interface StubOptions {
  profileError?: Error;
  runtimeError?: Error;
  configVersion?: number;
  profiles?: ProfileResponse[];
  observed?: ProfileRuntimeResponse["observed_state"];
}

function makeStub(options: StubOptions = {}) {
  const profiles = options.profiles ?? [profile()];
  let observed: ProfileRuntimeResponse["observed_state"] =
    options.observed ?? "running";
  const configVersion = options.configVersion ?? 1;
  const makeRuntime = (id: string) => runtime(id, observed, { config_version: configVersion });
  const spies = {
    profiles: {
      list: vi.fn(async () => profiles),
      get: vi.fn(async (id: string) => {
        if (options.profileError) throw options.profileError;
        return profiles.find((item) => item.id === id) ?? profiles[0]!;
      }),
      getRuntime: vi.fn(async (id: string) => {
        if (options.runtimeError) throw options.runtimeError;
        return makeRuntime(id);
      }),
      setDesiredState: vi.fn(async (id: string, state: "running" | "stopped") => {
        observed = state === "running" ? "running" : "stopped";
        return runtime(id, observed, { config_version: configVersion });
      }),
      stop: vi.fn(async (id: string) => {
        observed = "stopped";
        return runtime(id, "stopped");
      }),
    },
    groups: { list: vi.fn(async () => [] as GroupResponse[]) },
    proxies: { list: vi.fn(async () => [] as ProxyResponse[]) },
    fontSets: { list: vi.fn(async () => [] as FontSetInfo[]) },
  };
  return { client: spies as unknown as ApiClient, spies };
}

let stub: ReturnType<typeof makeStub>;

function renderPage(profileId = "p1") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={stub.client}>
              <SessionFocusProvider>
                <MemoryRouter initialEntries={[`/session/${profileId}`]}>
                  <Routes>
                    <Route path="/session/:profileId" element={<SessionPage />} />
                  </Routes>
                </MemoryRouter>
              </SessionFocusProvider>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

function resetHookState(stage: SessionStage = "connected"): void {
  hookState.stage = stage;
  hookState.diagnostics = {
    stage,
    profileId: "p1",
    connectionState: "connected",
    framesDecoded: 128,
  };
  hookState.errorMessage = null;
  hookState.reloadKey = 0;
  hookState.audioMuted = false;
  hookState.reconnect.mockClear();
  hookState.toggleAudio.mockClear();
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem("cbrowser.locale", "en");
  resetHookState();
  stub = makeStub();
});

describe("SessionPage", () => {
  it("running 时渲染 iframe，src 含 profileId", async () => {
    renderPage("p1");
    const iframe = await screen.findByTestId(SESS_IFRAME);
    expect(iframe.getAttribute("src")).toContain("p1");
    expect(screen.getByTestId(SESS_PAGE).getAttribute("data-stage")).toBe("connected");
  });

  it("非 connected 阶段显示 SESS_STAGE_PANEL", async () => {
    resetHookState("connecting_signaling");
    renderPage();
    expect(await screen.findByTestId(SESS_STAGE_PANEL)).toBeInTheDocument();
  });

  it("connected 不显示 SESS_STAGE_PANEL", async () => {
    renderPage();
    await screen.findByTestId(SESS_IFRAME);
    expect(screen.queryByTestId(SESS_STAGE_PANEL)).toBeNull();
  });

  it("专注模式切换前后同一 iframe DOM 节点不重建", async () => {
    const { container } = renderPage();
    await screen.findByTestId(SESS_IFRAME);
    const iframeBefore = container.querySelector("iframe");
    expect(iframeBefore).not.toBeNull();
    const focusToggle = within(screen.getByTestId(SESS_HEADER)).getByTestId("sess-focus-toggle");
    fireEvent.click(focusToggle);
    expect(focusToggle.getAttribute("aria-pressed")).toBe("true");
    expect(container.querySelector("iframe")).toBe(iframeBefore);
    fireEvent.mouseEnter(screen.getByTestId("sess-focus-hotzone"));
    expect(screen.getByTestId(SESS_FOCUS_TOOLBAR)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId(SESS_FOCUS_EXIT));
    expect(focusToggle.getAttribute("aria-pressed")).toBe("false");
    expect(container.querySelector("iframe")).toBe(iframeBefore);
  });

  it("detailsOpen 写 localStorage 并在重挂载后保持", async () => {
    const first = renderPage();
    fireEvent.click(within(await screen.findByTestId(SESS_HEADER)).getByTestId(SESS_DETAILS_TOGGLE));
    expect(localStorage.getItem("cbrowser.session.details_open")).toBe("1");
    first.unmount();
    renderPage();
    const panelToggle = within(await screen.findByTestId(SESS_DETAILS_PANEL)).getByTestId(SESS_DETAILS_TOGGLE);
    expect(panelToggle.getAttribute("aria-expanded")).toBe("true");
  });

  it("停止与音频回调触发", async () => {
    renderPage();
    const header = await screen.findByTestId(SESS_HEADER);
    fireEvent.click(within(header).getByTestId(SESS_STOP));
    await waitFor(() => expect(stub.spies.profiles.stop).toHaveBeenCalledWith("p1", expect.anything()));
    fireEvent.click(within(header).getByTestId(SESS_AUDIO_TOGGLE));
    expect(hookState.toggleAudio).toHaveBeenCalledTimes(1);
  });

  it("应用并重启回调触发（待应用判据成立）", async () => {
    stub = makeStub({ configVersion: 2 });
    renderPage();
    const header = await screen.findByTestId(SESS_HEADER);
    fireEvent.click(within(header).getByTestId(SESS_APPLY_RESTART));
    await waitFor(() =>
      expect(stub.spies.profiles.setDesiredState).toHaveBeenCalledWith("p1", "running", expect.anything()),
    );
  });

  it("诊断回调打开诊断浮层", async () => {
    renderPage();
    const header = await screen.findByTestId(SESS_HEADER);
    fireEvent.click(within(header).getByTestId(SESS_DIAG_TOGGLE));
    expect(screen.getByTestId(sessId("diag", "overlay"))).toBeInTheDocument();
  });

  it("诊断浮层按五种 audioStatus 渲染本地化文案", async () => {
    const statusKeys: Array<
      [NonNullable<SessionDiagnosticsData["audioStatus"]>, keyof typeof en]
    > = [
      ["normal", "audioStatusNormal"],
      ["no_track", "audioStatusNoTrack"],
      ["no_data", "audioStatusNoData"],
      ["unknown", "audioStatusUnknown"],
      ["muted", "audioStatusMuted"],
    ];
    const dictionaries = [
      ["en", en],
      ["zh", zh],
    ] as const;
    for (const [locale, dict] of dictionaries) {
      localStorage.setItem("cbrowser.locale", locale);
      for (const [status, key] of statusKeys) {
        hookState.diagnostics = {
          ...hookState.diagnostics,
          audioStatus: status,
        };
        const view = renderPage();
        const header = await screen.findByTestId(SESS_HEADER);
        fireEvent.click(within(header).getByTestId(SESS_DIAG_TOGGLE));
        expect(
          screen.getByTestId(sessId("diag", "audio-status")),
        ).toHaveTextContent(dict[key]);
        view.unmount();
      }
    }
  });

  it("stopping runtime 使用单一 stopping 阶段，不暴露 launch 动作", async () => {
    stub = makeStub({ observed: "stopping" });
    renderPage();
    const pageEl = await screen.findByTestId(SESS_PAGE);
    await waitFor(() =>
      expect(pageEl).toHaveAttribute("data-stage", "stopping"),
    );
    expect(screen.getByTestId(SESS_STAGE_PANEL)).toBeInTheDocument();
    expect(
      screen.getByTestId(sessId("stage-action", "view-status")),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId(sessId("stage-action", "launch")),
    ).toBeNull();
    expect(screen.getByTestId(SESS_STAGE)).toHaveAttribute(
      "data-stage",
      "stopping",
    );
    expect(screen.getByTestId(SESS_IFRAME)).toHaveAttribute(
      "data-stage",
      "stopping",
    );
  });

  it("error runtime 使用单一 error 阶段与对应动作", async () => {
    stub = makeStub({ observed: "error" });
    renderPage();
    const pageEl = await screen.findByTestId(SESS_PAGE);
    await waitFor(() => expect(pageEl).toHaveAttribute("data-stage", "error"));
    expect(screen.getByTestId(SESS_STAGE_PANEL)).toBeInTheDocument();
    expect(
      screen.getByTestId(sessId("stage-action", "reconnect")),
    ).toBeInTheDocument();
    expect(screen.getByTestId(SESS_STAGE)).toHaveAttribute(
      "data-stage",
      "error",
    );
    expect(screen.getByTestId(SESS_IFRAME)).toHaveAttribute(
      "data-stage",
      "error",
    );
  });

  it("stopped runtime 使用单一 runtime_not_ready 阶段并提供 launch", async () => {
    stub = makeStub({ observed: "stopped" });
    renderPage();
    const pageEl = await screen.findByTestId(SESS_PAGE);
    await waitFor(() =>
      expect(pageEl).toHaveAttribute("data-stage", "runtime_not_ready"),
    );
    expect(screen.getByTestId(SESS_STAGE_PANEL)).toBeInTheDocument();
    expect(
      screen.getByTestId(sessId("stage-action", "launch")),
    ).toBeInTheDocument();
    expect(screen.getByTestId(SESS_STAGE)).toHaveAttribute(
      "data-stage",
      "runtime_not_ready",
    );
    expect(screen.getByTestId(SESS_IFRAME)).toHaveAttribute(
      "data-stage",
      "runtime_not_ready",
    );
  });

  it("profile 404 显示 not-found 分支", async () => {
    stub = makeStub({ profileError: new ApiError("not found", 404) });
    renderPage();
    expect(await screen.findByTestId(sessId("not-found", "p1"))).toHaveTextContent(en.profileNotFound);
  });

  it("profile 加载失败显示 load-error 分支", async () => {
    stub = makeStub({ profileError: new ApiError("boom", 500) });
    renderPage();
    const box = await screen.findByTestId(sessId("load-error", "p1"));
    expect(box).toHaveTextContent("boom");
  });

  it("runtime_not_ready 阶段显示启动操作并点击触发 setDesiredState", async () => {
    resetHookState("runtime_not_ready");
    renderPage("p1");
    const launch = await screen.findByTestId(sessId("stage-action", "launch"));
    expect(launch).toHaveTextContent(en.launchRemoteBrowser);
    fireEvent.click(launch);
    await waitFor(() =>
      expect(stub.spies.profiles.setDesiredState).toHaveBeenCalledWith(
        "p1",
        "running",
        expect.anything(),
      ),
    );
  });

  it("启动失败显示 danger Banner", async () => {
    stub.spies.profiles.setDesiredState.mockImplementation(async () => {
      throw new Error("launch failed");
    });
    resetHookState("runtime_not_ready");
    renderPage("p1");
    fireEvent.click(await screen.findByTestId(sessId("stage-action", "launch")));
    const banner = await screen.findByTestId(sessId("launch", "error"));
    expect(banner).toHaveAttribute("role", "alert");
    expect(banner).toHaveTextContent(
      en.sessionStartFailed.replace("{error}", "launch failed"),
    );
  });

  it("请求 pending 显示 loading 分支", async () => {
    stub.spies.profiles.get.mockImplementation(
      () => new Promise<ProfileResponse>(() => undefined),
    );
    renderPage("p1");
    expect(await screen.findByTestId(sessId("loading", "p1"))).toBeInTheDocument();
  });

  it("runtime 请求失败显示 load-error 而非 stopped", async () => {
    stub = makeStub({ runtimeError: new Error("runtime down") });
    renderPage("p1");
    const box = await screen.findByTestId(sessId("load-error", "p1"));
    expect(box).toHaveTextContent(
      en.sessionLoadFailed.replace("{error}", "runtime down"),
    );
    expect(screen.queryByTestId(SESS_STAGE_PANEL)).toBeNull();
    expect(screen.getByTestId(SESS_PAGE).getAttribute("data-stage")).not.toBe("stopped");
  });

  it("runtime 错误分支只重试 runtime 查询", async () => {
    stub = makeStub({ runtimeError: new Error("runtime down") });
    renderPage("p1");
    const box = await screen.findByTestId(sessId("load-error", "p1"));
    const getCalls = stub.spies.profiles.get.mock.calls.length;
    const runtimeCalls = stub.spies.profiles.getRuntime.mock.calls.length;
    fireEvent.click(within(box).getByTestId(sessId("load-retry", "profile")));
    await waitFor(() =>
      expect(stub.spies.profiles.getRuntime.mock.calls.length).toBe(runtimeCalls + 1),
    );
    expect(stub.spies.profiles.get.mock.calls.length).toBe(getCalls);
  });

  it("load-error 分支有 retry 按钮", async () => {
    stub = makeStub({ profileError: new ApiError("boom", 500) });
    renderPage("p1");
    const box = await screen.findByTestId(sessId("load-error", "p1"));
    const retry = within(box).getByTestId(sessId("load-retry", "profile"));
    expect(retry).toHaveTextContent(en.retryAction);
    const getCalls = stub.spies.profiles.get.mock.calls.length;
    fireEvent.click(retry);
    await waitFor(() =>
      expect(stub.spies.profiles.get.mock.calls.length).toBe(getCalls + 1),
    );
  });

  it("A 启动失败不污染 B", async () => {
    const launchStates = new Map<string, "error" | "success">([["pA", "error"]]);
    stub.spies.profiles.setDesiredState.mockImplementation(async (id: string) => {
      if (launchStates.get(id) === "error") throw new Error(`launch failed ${id}`);
      return runtime(id, "running");
    });
    resetHookState("runtime_not_ready");
    const viewA = renderPage("pA");
    fireEvent.click(await screen.findByTestId(sessId("stage-action", "launch")));
    expect(await screen.findByTestId(sessId("launch", "error"))).toHaveTextContent(
      "launch failed pA",
    );
    viewA.unmount();

    renderPage("pB");
    await screen.findByTestId(SESS_IFRAME);
    expect(screen.queryByTestId(sessId("launch", "error"))).toBeNull();
  });

  it("A pending 不 disable B，A 迟到失败也不污染 B", async () => {
    let rejectA: ((error: Error) => void) | undefined;
    const launchStates = new Map<string, "pending" | "success">([["pA", "pending"]]);
    stub.spies.profiles.setDesiredState.mockImplementation((id: string) => {
      if (launchStates.get(id) === "pending") {
        return new Promise<ProfileRuntimeResponse>((_resolve, reject) => {
          rejectA = reject;
        });
      }
      return Promise.resolve(runtime(id, "running"));
    });
    resetHookState("runtime_not_ready");
    const viewA = renderPage("pA");
    fireEvent.click(await screen.findByTestId(sessId("stage-action", "launch")));
    await waitFor(() =>
      expect(stub.spies.profiles.setDesiredState).toHaveBeenCalledWith(
        "pA",
        "running",
        expect.anything(),
      ),
    );
    viewA.unmount();

    renderPage("pB");
    const launchB = await screen.findByTestId(sessId("stage-action", "launch"));
    expect(launchB).not.toBeDisabled();
    fireEvent.click(launchB);
    await waitFor(() =>
      expect(stub.spies.profiles.setDesiredState).toHaveBeenCalledWith(
        "pB",
        "running",
        expect.anything(),
      ),
    );
    await act(async () => {
      rejectA?.(new Error("late A failure"));
    });
    expect(screen.queryByTestId(sessId("launch", "error"))).toBeNull();
  });

  it("返回 A 时 A 的动作状态重现", async () => {
    const launchStates = new Map<string, "error" | "success">([["pA", "error"]]);
    stub.spies.profiles.setDesiredState.mockImplementation(async (id: string) => {
      if (launchStates.get(id) === "error") throw new Error(`launch failed ${id}`);
      return runtime(id, "running");
    });
    resetHookState("runtime_not_ready");
    const viewA = renderPage("pA");
    fireEvent.click(await screen.findByTestId(sessId("stage-action", "launch")));
    expect(await screen.findByTestId(sessId("launch", "error"))).toHaveTextContent(
      "launch failed pA",
    );
    viewA.unmount();

    const viewB = renderPage("pB");
    await screen.findByTestId(SESS_IFRAME);
    expect(screen.queryByTestId(sessId("launch", "error"))).toBeNull();
    viewB.unmount();

    renderPage("pA");
    fireEvent.click(await screen.findByTestId(sessId("stage-action", "launch")));
    expect(await screen.findByTestId(sessId("launch", "error"))).toHaveTextContent(
      "launch failed pA",
    );
  });

  it("诊断浮层显示 connectionState 与 framesDecoded 指标值", async () => {
    renderPage();
    const header = await screen.findByTestId(SESS_HEADER);
    fireEvent.click(within(header).getByTestId(SESS_DIAG_TOGGLE));
    const overlay = screen.getByTestId(sessId("diag", "overlay"));
    expect(overlay).toHaveTextContent(en.sessionDiagConnectionState);
    expect(overlay).toHaveTextContent("connected");
    expect(overlay).toHaveTextContent(en.sessionDiagFramesDecoded);
    expect(overlay).toHaveTextContent("128");
  });
});
