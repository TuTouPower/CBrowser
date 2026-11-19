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
  // jsdom has PointerEvent but no pointer capture: Radix calls
  // hasPointerCapture on the trigger in its pointerdown handler.
  if (typeof Element.prototype.hasPointerCapture !== "function") {
    Element.prototype.hasPointerCapture = () => false;
    Element.prototype.releasePointerCapture = () => undefined;
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
    humanize: false,
    human_preset: "default",
    geoip: true,
    clipboard_sync: true,
    auto_launch: false,
    color_scheme: "light",
    include_cjk_fonts: false,
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

function makeStub(opts: {
  groups?: GroupResponse[];
  proxies?: ProxyResponse[];
} = {}) {
  return {
    groups: {
      list: vi.fn(async () => opts.groups ?? []),
      create: vi.fn(async (data: { name: string }) => ({ ...group(), ...data })),
    },
    proxies: { list: vi.fn(async () => opts.proxies ?? []) },
    fontSets: {
      list: vi.fn(async () => ({ items: [], default_font_set_id: {} })),
    },
  } as unknown as ApiClient;
}

function renderForm(opts: {
  mode: "create" | "edit";
  initial?: ProfileResponse;
  onSubmit?: (
    values: ProfileCreateRequest | ProfileUpdateRequest,
  ) => Promise<void>;
  submitLabel?: string;
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





  it("submits the new advanced-option defaults in the create form", async () => {
    const onSubmit = vi.fn(async () => undefined);
    renderForm({ mode: "create", stub: makeStub(), onSubmit });
    fireEvent.change(screen.getByTestId("profile-form-name"), {
      target: { value: "Defaults" },
    });
    fireEvent.click(screen.getByTestId("profile-form-submit"));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        humanize: true,
        portable_cookies: true,
        transparent_proxy: false,
        auto_launch: false,
        allow_3p_cookies: true,
        set_google_default: true,
        clipboard_sync: true,
        restore_session: true,
        capture_preview: true,
        locale: "en-US",
      }),
    );
  });

  it("links language to the timezone and allows a manual override", async () => {
    const onSubmit = vi.fn(async () => undefined);
    renderForm({ mode: "create", stub: makeStub(), onSubmit });
    const tz = screen.getByTestId("profile-form-timezone");
    const localeBox = within(
      screen.getByTestId("profile-form-locale"),
    ).getByRole("combobox");

    fireEvent.focus(tz);
    fireEvent.change(tz, { target: { value: "Asia/Shanghai" } });
    fireEvent.keyDown(tz, { key: "Enter" });
    await waitFor(() => expect(tz).toHaveValue("Asia/Shanghai"));
    expect(localeBox.textContent).toContain(en.formLocaleChinese);

    fireEvent.focus(tz);
    fireEvent.change(tz, { target: { value: "Europe/London" } });
    fireEvent.keyDown(tz, { key: "Enter" });
    await waitFor(() => expect(tz).toHaveValue("Europe/London"));
    expect(localeBox.textContent).toContain(en.formLocaleEnglish);

    fireEvent.click(localeBox);
    fireEvent.click(
      await screen.findByRole("option", { name: en.formLocaleChinese }),
    );
    fireEvent.change(screen.getByTestId("profile-form-name"), {
      target: { value: "Linked" },
    });
    fireEvent.click(screen.getByTestId("profile-form-submit"));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ timezone: "Europe/London", locale: "zh-CN" }),
    );
  });

  it("keeps the language when the timezone is cleared to auto", async () => {
    const onSubmit = vi.fn(async () => undefined);
    renderForm({ mode: "create", stub: makeStub(), onSubmit });
    const tz = screen.getByTestId("profile-form-timezone");
    fireEvent.focus(tz);
    fireEvent.change(tz, { target: { value: "Asia/Shanghai" } });
    fireEvent.keyDown(tz, { key: "Enter" });
    await waitFor(() => expect(tz).toHaveValue("Asia/Shanghai"));
    const localeBox = within(
      screen.getByTestId("profile-form-locale"),
    ).getByRole("combobox");
    expect(localeBox.textContent).toContain(en.formLocaleChinese);

    fireEvent.focus(tz);
    fireEvent.change(tz, { target: { value: "" } });
    fireEvent.keyDown(tz, { key: "Enter" });
    await waitFor(() => expect(tz).toHaveValue(""));
    expect(localeBox.textContent).toContain(en.formLocaleChinese);

    fireEvent.change(screen.getByTestId("profile-form-name"), {
      target: { value: "Auto" },
    });
    fireEvent.click(screen.getByTestId("profile-form-submit"));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ timezone: null, locale: "zh-CN" }),
    );
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

  it("aligns timezone, language, and CJK inclusion when selecting a proxy, keeps manual overrides, and resets alignment on request", async () => {
    const usProxy: ProxyResponse = {
      ...proxy(),
      id: "px-us",
      name: "US West Node",
      country_code: "US",
      region_label: "Los Angeles",
    };
    const hkProxy: ProxyResponse = {
      ...proxy(),
      id: "px-hk",
      name: "HK Node",
      country_code: "HK",
      region_label: "Hong Kong",
    };
    const onSubmit = vi.fn(async () => undefined);
    renderForm({
      mode: "create",
      stub: makeStub({ proxies: [usProxy, hkProxy] }),
      onSubmit,
    });

    const cjkCheckbox = () =>
      within(screen.getByTestId("profile-form-include-cjk")).getByRole(
        "checkbox",
      );

    await screen.findByTestId("profile-form-name");

    // 1. Pick US proxy -> US timezone, en-US locale, CJK fonts excluded
    fireEvent.click(
      within(screen.getByTestId("profile-form-proxy")).getByRole("combobox"),
    );
    fireEvent.click(
      await screen.findByRole("option", { name: "US West Node" }),
    );
    expect(screen.getByTestId("profile-form-timezone")).toHaveValue(
      "America/Los_Angeles",
    );
    expect(
      within(screen.getByTestId("profile-form-locale")).getByRole("combobox")
        .textContent,
    ).toContain(en.formLocaleEnglish);
    expect(cjkCheckbox()).toHaveAttribute("aria-checked", "false");
    expect(
      screen.getByTestId("profile-form-alignment-summary").textContent,
    ).toContain(en.formAlignFontsEn);

    // 2. Switch to HK proxy -> Hong Kong timezone, zh-CN locale, CJK included
    fireEvent.click(
      within(screen.getByTestId("profile-form-proxy")).getByRole("combobox"),
    );
    fireEvent.click(await screen.findByRole("option", { name: "HK Node" }));
    expect(screen.getByTestId("profile-form-timezone")).toHaveValue(
      "Asia/Hong_Kong",
    );
    expect(
      within(screen.getByTestId("profile-form-locale")).getByRole("combobox")
        .textContent,
    ).toContain(en.formLocaleChinese);
    expect(cjkCheckbox()).toHaveAttribute("aria-checked", "true");
    expect(
      screen.getByTestId("profile-form-alignment-summary").textContent,
    ).toContain(en.formAlignFontsZh);

    // 3. Switch back to US proxy, then manually override locale to zh-CN
    fireEvent.click(
      within(screen.getByTestId("profile-form-proxy")).getByRole("combobox"),
    );
    fireEvent.click(
      await screen.findByRole("option", { name: "US West Node" }),
    );
    fireEvent.click(
      within(screen.getByTestId("profile-form-locale")).getByRole("combobox"),
    );
    fireEvent.click(
      await screen.findByRole("option", { name: en.formLocaleChinese }),
    );
    expect(
      screen.getByTestId("profile-form-alignment-summary").textContent,
    ).toContain(en.formAlignManualNote);
    expect(cjkCheckbox()).toHaveAttribute("aria-checked", "true");

    // 4. Reset alignment restores proxy defaults (US timezone + en-US + CJK off)
    fireEvent.click(screen.getByTestId("profile-form-reset-alignment"));
    expect(screen.getByTestId("profile-form-timezone")).toHaveValue(
      "America/Los_Angeles",
    );
    expect(
      within(screen.getByTestId("profile-form-locale")).getByRole("combobox")
        .textContent,
    ).toContain(en.formLocaleEnglish);
    expect(cjkCheckbox()).toHaveAttribute("aria-checked", "false");

    fireEvent.change(screen.getByTestId("profile-form-name"), {
      target: { value: "US Env" },
    });
    fireEvent.click(screen.getByTestId("profile-form-submit"));
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        proxy_id: "px-us",
        timezone: "America/Los_Angeles",
        locale: "en-US",
        include_cjk_fonts: false,
      }),
    );
    // The font set binding is backend-managed (t075): the create
    // payload no longer carries a font_set_id at all.
    expect(onSubmit).not.toHaveBeenCalledWith(
      expect.objectContaining({ font_set_id: expect.anything() }),
    );
  });

  it("keeps a manually toggled CJK switch across later language changes", async () => {
    renderForm({ mode: "create", stub: makeStub() });
    const cjkCheckbox = () =>
      within(screen.getByTestId("profile-form-include-cjk")).getByRole(
        "checkbox",
      );
    await screen.findByTestId("profile-form-name");
    expect(cjkCheckbox()).toHaveAttribute("aria-checked", "false");

    // User turns CJK on for an English profile; switching the language
    // afterwards must not silently revert the explicit choice.
    fireEvent.click(cjkCheckbox());
    expect(cjkCheckbox()).toHaveAttribute("aria-checked", "true");
    fireEvent.click(
      within(screen.getByTestId("profile-form-locale")).getByRole("combobox"),
    );
    fireEvent.click(
      await screen.findByRole("option", { name: en.formLocaleChinese }),
    );
    expect(cjkCheckbox()).toHaveAttribute("aria-checked", "true");
    fireEvent.click(
      within(screen.getByTestId("profile-form-locale")).getByRole("combobox"),
    );
    fireEvent.click(
      await screen.findByRole("option", { name: en.formLocaleEnglish }),
    );
    expect(cjkCheckbox()).toHaveAttribute("aria-checked", "true");
  });

  it("aligns timezone to Asia/Shanghai when locale is switched on an unassigned form", async () => {
    const onSubmit = vi.fn(async () => undefined);
    renderForm({ mode: "create", stub: makeStub(), onSubmit });

    const localeBox = within(
      screen.getByTestId("profile-form-locale"),
    ).getByRole("combobox");
    fireEvent.click(localeBox);
    fireEvent.click(
      await screen.findByRole("option", { name: en.formLocaleChinese }),
    );
    expect(screen.getByTestId("profile-form-timezone")).toHaveValue(
      "Asia/Shanghai",
    );
  });

  it("detects saved proxy deviation after async proxy fetch, resets cleanly, and preserves matched edit alignment (t090 AC-001)", async () => {
    const jpProxy: ProxyResponse = {
      ...proxy(),
      id: "px-jp",
      name: "Tokyo Relay",
      country_code: "JP",
      region_label: "Tokyo",
    };
    let resolveProxies!: (items: ProxyResponse[]) => void;
    const delayedStub = {
      ...makeStub(),
      proxies: {
        list: vi.fn(
          () =>
            new Promise<ProxyResponse[]>((resolve) => {
              resolveProxies = resolve;
            }),
        ),
      },
    } as unknown as ApiClient;

    renderForm({
      mode: "edit",
      initial: profile({
        id: "prof-jp-misaligned",
        proxy_id: "px-jp",
        timezone: "Asia/Shanghai",
        locale: "zh-CN",
        include_cjk_fonts: true,
      }),
      stub: delayedStub,
    });

    await screen.findByTestId("profile-form-name");
    resolveProxies([jpProxy]);

    await waitFor(() => {
      expect(
        screen.queryByTestId("profile-form-reset-alignment"),
      ).toBeInTheDocument();
    });
    const summaryMismatch = screen.getByTestId(
      "profile-form-alignment-summary",
    ).textContent ?? "";
    expect(summaryMismatch).not.toContain("Aligned to proxy");
    expect(summaryMismatch).toContain("Asia/Shanghai");
    expect(summaryMismatch).toContain(en.formAlignManualNote);

    fireEvent.click(screen.getByTestId("profile-form-reset-alignment"));
    expect(screen.getByTestId("profile-form-timezone")).toHaveValue(
      "Asia/Tokyo",
    );
    expect(
      within(screen.getByTestId("profile-form-locale")).getByRole("combobox")
        .textContent,
    ).toContain(en.formLocaleEnglish);
    expect(
      within(screen.getByTestId("profile-form-include-cjk")).getByRole(
        "checkbox",
      ),
    ).toHaveAttribute("aria-checked", "false");
    expect(
      screen.queryByTestId("profile-form-reset-alignment"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByTestId("profile-form-alignment-summary").textContent,
    ).toContain("Aligned to proxy (JP)");
    expect(
      screen.getByTestId("profile-form-alignment-summary").textContent,
    ).toContain(en.formAlignFontsEn);

    // Timezone-only mismatch on reopen also triggers deviation notice + reset.
    const tzOnlyView = renderForm({
      mode: "edit",
      initial: profile({
        id: "prof-jp-tz-only",
        proxy_id: "px-jp",
        timezone: "Europe/London",
        locale: "en-US",
        include_cjk_fonts: false,
      }),
      stub: makeStub({ proxies: [jpProxy] }),
    });
    await waitFor(() => {
      expect(
        within(tzOnlyView.container).queryByTestId("profile-form-reset-alignment"),
      ).toBeInTheDocument();
    });
    expect(
      within(tzOnlyView.container).getByTestId("profile-form-alignment-summary")
        .textContent,
    ).not.toContain("Aligned to proxy");
    tzOnlyView.unmount();

    // Exact saved alignment shows aligned banner without a reset button.
    const matchedView = renderForm({
      mode: "edit",
      initial: profile({
        id: "prof-jp-matched",
        proxy_id: "px-jp",
        timezone: "Asia/Tokyo",
        locale: "en-US",
        include_cjk_fonts: false,
      }),
      stub: makeStub({ proxies: [jpProxy] }),
    });
    await waitFor(() => {
      expect(
        within(matchedView.container).getByTestId("profile-form-alignment-summary")
          .textContent,
      ).toContain("Aligned to proxy (JP)");
    });
    expect(
      within(matchedView.container).queryByTestId("profile-form-reset-alignment"),
    ).not.toBeInTheDocument();
    matchedView.unmount();
  });

  it("renders CJK alignment summary from actual include_cjk_fonts across init, toggle, and reset (t090 AC-002)", async () => {
    const view = renderForm({
      mode: "edit",
      initial: profile({
        id: "prof-cjk-en",
        timezone: "Asia/Tokyo",
        locale: "en-US",
        include_cjk_fonts: true,
      }),
      stub: makeStub(),
    });
    await screen.findByTestId("profile-form-name");
    expect(
      screen.getByTestId("profile-form-alignment-summary").textContent,
    ).toContain(en.formAlignFontsZh);

    const cjkCheckbox = within(
      screen.getByTestId("profile-form-include-cjk"),
    ).getByRole("checkbox");
    fireEvent.click(cjkCheckbox);
    expect(cjkCheckbox).toHaveAttribute("aria-checked", "false");
    expect(
      screen.getByTestId("profile-form-alignment-summary").textContent,
    ).toContain(en.formAlignFontsEn);
    view.unmount();

    const cnProxy: ProxyResponse = {
      ...proxy(),
      id: "px-cn",
      name: "Shanghai Node",
      country_code: "CN",
      region_label: "Shanghai",
    };
    const resetStub = {
      ...makeStub(),
      proxies: { list: vi.fn().mockResolvedValue([cnProxy]) },
    } as unknown as ApiClient;
    renderForm({
      mode: "edit",
      initial: profile({
        id: "prof-zh-nocjk",
        proxy_id: "px-cn",
        timezone: "Asia/Tokyo",
        locale: "zh-CN",
        include_cjk_fonts: false,
      }),
      stub: resetStub,
    });
    await screen.findByTestId("profile-form-name");
    expect(
      screen.getByTestId("profile-form-alignment-summary").textContent,
    ).toContain(en.formAlignFontsEn);

    const resetBtn = await screen.findByTestId("profile-form-reset-alignment");
    fireEvent.click(resetBtn);
    expect(
      screen.getByTestId("profile-form-alignment-summary").textContent,
    ).toContain(en.formAlignFontsZh);
  });

  it("does not overwrite proxy or saved non-null timezone when locale changes (t090 AC-003)", async () => {
    const jpProxy: ProxyResponse = {
      ...proxy(),
      id: "px-jp",
      name: "Tokyo Relay",
      country_code: "JP",
      region_label: "Tokyo",
    };
    const createView = renderForm({
      mode: "create",
      stub: makeStub({ proxies: [jpProxy] }),
    });
    await screen.findByTestId("profile-form-name");

    fireEvent.click(
      within(screen.getByTestId("profile-form-proxy")).getByRole("combobox"),
    );
    fireEvent.click(await screen.findByRole("option", { name: "Tokyo Relay" }));
    expect(screen.getByTestId("profile-form-timezone")).toHaveValue(
      "Asia/Tokyo",
    );

    fireEvent.click(
      within(screen.getByTestId("profile-form-locale")).getByRole("combobox"),
    );
    fireEvent.click(
      await screen.findByRole("option", { name: en.formLocaleChinese }),
    );
    expect(screen.getByTestId("profile-form-timezone")).toHaveValue(
      "Asia/Tokyo",
    );
    createView.unmount();

    renderForm({
      mode: "edit",
      initial: profile({
        id: "prof-berlin",
        proxy_id: null,
        timezone: "Europe/Berlin",
        locale: "en-US",
        include_cjk_fonts: false,
      }),
      stub: makeStub(),
    });
    await screen.findByTestId("profile-form-name");
    fireEvent.click(
      within(screen.getByTestId("profile-form-locale")).getByRole("combobox"),
    );
    fireEvent.click(
      await screen.findByRole("option", { name: en.formLocaleChinese }),
    );
    expect(screen.getByTestId("profile-form-timezone")).toHaveValue(
      "Europe/Berlin",
    );
  });

  // t058 A24: the two onDirtyRuntimeConfig cases below were deleted with
  // the prop (ConfigTab no longer splits the submit by dirty class; the
  // diff carries it). The classification itself is covered by
  // profile_field_diff.test.ts. The "submits the full values in edit
  // mode" case was deleted because edit now submits only the diff; see
  // ProfileForm.t058.test.tsx (AC-001/AC-002).
  //
  // t075: the five font-set selection cases (backend-default preselect,
  // explicit-none via mouse/keyboard/touch, integrity warning) were
  // deleted wholesale — the form no longer selects font sets at all;
  // the binding is backend-managed and the form carries only the CJK
  // inclusion switch (covered by the alignment cases above).
});

describe("ProfileForm (t077)", () => {
  it("proxy select is searchable and Enter picks the filtered match (AC-003)", async () => {
    const zebra: ProxyResponse = {
      ...proxy(),
      id: "px-zebra",
      name: "Zebra Node",
      country_code: "US",
      region_label: "Los Angeles",
    };
    renderForm({
      mode: "create",
      stub: makeStub({ proxies: [proxy(), zebra] }),
    });
    await screen.findByTestId("profile-form-name");
    fireEvent.click(
      within(screen.getByTestId("profile-form-proxy")).getByRole("combobox"),
    );
    const search = await screen.findByLabelText(en.proxySearch);
    fireEvent.change(search, { target: { value: "Zebra" } });
    expect(
      screen.queryByRole("option", { name: "Proxy A" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Zebra Node" }),
    ).toBeInTheDocument();
    fireEvent.keyDown(search, { key: "Enter" });
    await waitFor(() =>
      expect(
        within(screen.getByTestId("profile-form-proxy")).getByRole("combobox")
          .textContent,
      ).toContain("Zebra Node"),
    );
  });

  it("group select is searchable (AC-003)", async () => {
    renderForm({
      mode: "create",
      stub: makeStub({ proxies: [proxy()], groups: [group()] }),
    });
    await screen.findByTestId("profile-form-name");
    fireEvent.click(
      within(screen.getByTestId("profile-form-group")).getByRole("combobox"),
    );
    const search = await screen.findByLabelText(en.searchGroups);
    fireEvent.change(search, { target: { value: "Work" } });
    expect(
      screen.getByRole("option", { name: "Work" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("option", { name: en.formNewGroup }),
    ).not.toBeInTheDocument();
  });

  it("every advanced option and extra parameter field has a keyboard-readable help trigger (AC-006)", async () => {
    renderForm({ mode: "create", stub: makeStub() });
    await screen.findByTestId("profile-form-name");
    const fields = [
      en.formHumanize,
      en.formClipboardSync,
      en.formAutoLaunch,
      en.formAllow3pCookies,
      en.formSetGoogleDefault,
      en.formRestoreSession,
      en.formTransparentProxy,
      en.formPortableCookies,
      en.formCapturePreview,
      en.formHumanPreset,
      en.formLaunchArgs,
      en.formExtensionPaths,
    ];
    for (const field of fields) {
      expect(
        screen.getByRole("button", {
          name: en.formShowHelp.replace("{field}", field),
        }),
      ).toBeInTheDocument();
    }
    // Keyboard focus opens the tooltip with the real help text.
    const humanizeHelp = screen.getByRole("button", {
      name: en.formShowHelp.replace("{field}", en.formHumanize),
    });
    fireEvent.focus(humanizeHelp);
    expect(await screen.findByRole("tooltip")).toHaveTextContent(
      en.formHumanizeHelp,
    );
  });

  it("seed input is compact and the reseed button sits on the label row (AC-002)", async () => {
    renderForm({ mode: "create", stub: makeStub() });
    await screen.findByTestId("profile-form-name");
    const seedInput = screen.getByLabelText(en.formSeed) as HTMLInputElement;
    expect(seedInput.className).toContain("w-seed");
    const reseed = screen.getByTestId("profile-form-reseed");
    // The reseed button shares its parent row with the field label.
    expect(reseed.parentElement?.textContent).toContain(en.formSeed);
    expect(reseed.parentElement?.textContent).not.toContain(
      String(seedInput.value),
    );
  });

  it("every select trigger fills its field width so a long value truncates instead of overflowing the column (AC-001/AC-007)", async () => {
    // Chrome sizes a button's width:auto to its content even with
    // display:flex, so a bare trigger in a narrow grid cell blows
    // out to its full text width (real browser: 954px in a 256px
    // box) instead of truncating. The form's selects carry w-full
    // so they fill their grid cell and the truncate span inside can
    // shrink. (Geometry itself is proven by the t077 browser
    // probe's long-value scene; this pins the class at each site.)
    renderForm({ mode: "create", stub: makeStub() });
    await screen.findByTestId("profile-form-name");
    for (const name of [
      en.formGroup,
      en.formProxy,
      en.formLocale,
      en.formPlatform,
      en.formColorScheme,
      en.formHumanPreset,
    ]) {
      const trigger = screen.getByRole("combobox", { name });
      expect(trigger.className).toContain("w-full");
    }
  });
});
