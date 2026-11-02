import { describe, expect, it, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import { I18nProvider, useI18n } from "./i18n";

function Probe() {
  const { locale, setLocale } = useI18n();
  return (
    <button onClick={() => setLocale(locale === "zh" ? "en" : "zh")} data-testid="switch">
      {locale}
    </button>
  );
}

describe("i18n", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.lang = "";
  });

  it("migrates the legacy locale key and syncs document language", async () => {
    localStorage.setItem("cbm.locale", "zh");
    const view = render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    );
    expect(view.getByTestId("switch").textContent).toBe("zh");
    expect(localStorage.getItem("cbrowser.locale")).toBe("zh");
    expect(localStorage.getItem("cbm.locale")).toBeNull();
    await waitFor(() => expect(document.documentElement.lang).toBe("zh"));
    view.getByTestId("switch").click();
    await waitFor(() => expect(document.documentElement.lang).toBe("en"));
  });
});
