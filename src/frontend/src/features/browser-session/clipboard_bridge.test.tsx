import { afterEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render } from "@testing-library/react";
import { I18nProvider } from "../../i18n";
import { ClipboardPermissionHint } from "./ClipboardPermissionHint";
import { readClipboardPermission } from "./clipboard_bridge";

function mockPermissions(states: Record<string, string>) {
  Object.defineProperty(navigator, "permissions", {
    configurable: true,
    value: {
      query: vi.fn(async ({ name }: { name: string }) => ({
        state: states[name] ?? "prompt",
      })),
    },
  });
}

describe("clipboard bridge", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    // @ts-expect-error remove test-only permissions stub
    delete navigator.permissions;
  });

  it("reports denied when either clipboard permission is denied", async () => {
    mockPermissions({ "clipboard-read": "granted", "clipboard-write": "denied" });
    await expect(readClipboardPermission()).resolves.toBe("denied");
  });

  it("reports granted only when both directions are granted", async () => {
    mockPermissions({ "clipboard-read": "granted", "clipboard-write": "granted" });
    await expect(readClipboardPermission()).resolves.toBe("granted");
  });

  it("shows a prompt hint before the user grants access", async () => {
    mockPermissions({ "clipboard-read": "prompt", "clipboard-write": "granted" });
    const view = render(
      <I18nProvider>
        <ClipboardPermissionHint />
      </I18nProvider>,
    );
    const hint = await view.findByTestId("clipboard-permission-hint");
    expect(hint).toHaveAttribute("data-clipboard-permission", "prompt");
    expect(hint).toHaveTextContent(/requested/i);
  });

  it("shows an actionable hint and never reads or writes clipboard data", async () => {
    mockPermissions({ "clipboard-read": "denied", "clipboard-write": "denied" });
    const readText = vi.fn();
    const writeText = vi.fn();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { readText, writeText },
    });
    const view = render(
      <I18nProvider>
        <ClipboardPermissionHint />
      </I18nProvider>,
    );
    const hint = await view.findByTestId("clipboard-permission-hint");
    expect(hint).toHaveAttribute("data-clipboard-permission", "denied");
    expect(hint).toHaveTextContent(/allow clipboard access/i);
    expect(readText).not.toHaveBeenCalled();
    expect(writeText).not.toHaveBeenCalled();
  });
});
