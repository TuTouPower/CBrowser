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
