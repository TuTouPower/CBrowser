import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { I18nProvider, en } from "../../i18n";
import { ClipboardPermissionHint } from "./ClipboardPermissionHint";
import { sessId } from "./session_keys";

const HINT_ID = sessId("clipboard", "hint");

function stubPermissions(state: string) {
  const query = vi.fn(async () => ({ state }));
  Object.defineProperty(navigator, "permissions", {
    configurable: true,
    value: { query },
  });
  return query;
}

function stubClipboard() {
  const clipboard = {
    read: async () => "",
    write: async (_data: unknown) => undefined,
  };
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: clipboard,
  });
  return {
    read: vi.spyOn(clipboard, "read"),
    write: vi.spyOn(clipboard, "write"),
  };
}

function renderHint() {
  return render(
    <I18nProvider>
      <ClipboardPermissionHint />
    </I18nProvider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("cbrowser.locale", "en");
});

afterEach(() => {
  vi.restoreAllMocks();
  Reflect.deleteProperty(navigator, "permissions");
  Reflect.deleteProperty(navigator, "clipboard");
});

describe("ClipboardPermissionHint", () => {
  it("未授权时按设计系统显示剪贴板权限提示", async () => {
    const query = stubPermissions("denied");
    renderHint();
    const hint = await screen.findByTestId(HINT_ID);
    expect(query).toHaveBeenCalledWith({ name: "clipboard-read" });
    expect(hint).toHaveAttribute("data-clipboard-permission", "denied");
    expect(hint).toHaveAttribute("role", "status");
    expect(hint).toHaveTextContent(en.clipboardPermissionDenied);
    expect(hint).toHaveTextContent(en.clipboardPermissionDeniedHint);
  });

  it("从不读写剪贴板数据", async () => {
    const spies = stubClipboard();
    stubPermissions("prompt");
    renderHint();
    const hint = await screen.findByTestId(HINT_ID);
    expect(hint).toHaveAttribute("data-clipboard-permission", "prompt");
    expect(spies.read).not.toHaveBeenCalled();
    expect(spies.write).not.toHaveBeenCalled();
  });
});
