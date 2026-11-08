import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { en, zh, I18nProvider, useI18n } from "./i18n";

function Probe() {
  const { locale, setLocale } = useI18n();
  return (
    <button onClick={() => setLocale(locale === "zh" ? "en" : "zh")} data-testid="switch">
      {locale}
    </button>
  );
}

describe("i18n dictionaries", () => {
  it("keeps the zh key set exactly equal to the en key set", () => {
    expect(Object.keys(zh).sort()).toEqual(Object.keys(en).sort());
  });

  it("has a non-empty translation for every key in both locales", () => {
    for (const key of Object.keys(en) as (keyof typeof en)[]) {
      expect(en[key]).not.toBe("");
      expect(zh[key]).not.toBe("");
    }
  });
});

describe("i18n current storage key", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.lang = "";
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    document.documentElement.lang = "";
  });

  it("reads cbrowser.locale, syncs document language and saves switches to the current key", async () => {
    localStorage.setItem("cbrowser.locale", "zh");
    const view = render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    expect(view.getByTestId("switch").textContent).toBe("zh");
    await waitFor(() => expect(document.documentElement.lang).toBe("zh"));
    view.getByTestId("switch").click();
    await waitFor(() => expect(document.documentElement.lang).toBe("en"));
    expect(localStorage.getItem("cbrowser.locale")).toBe("en");
  });

  it("defaults to the browser language when no current key is stored", async () => {
    vi.spyOn(window.navigator, "language", "get").mockReturnValue("zh-CN");
    const view = render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    expect(view.getByTestId("switch").textContent).toBe("zh");
    await waitFor(() => expect(document.documentElement.lang).toBe("zh"));
  });
});

describe("legacy cbm.locale migration is discontinued", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.lang = "";
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    document.documentElement.lang = "";
  });

  it("ignores cbm.locale and applies the default rules without migrating", () => {
    vi.spyOn(window.navigator, "language", "get").mockReturnValue("en-US");
    localStorage.setItem("cbm.locale", "zh");
    const view = render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    expect(view.getByTestId("switch").textContent).toBe("en");
    expect(localStorage.getItem("cbrowser.locale")).toBeNull();
    expect(localStorage.getItem("cbm.locale")).toBe("zh");
  });
});
