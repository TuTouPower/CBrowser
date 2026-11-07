import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { I18nProvider, en } from "../../i18n";
import {
  FocusModeToolbar,
  type FocusModeToolbarProps,
} from "./FocusModeToolbar";
import { SESS_FOCUS_EXIT, SESS_FOCUS_TOOLBAR } from "./session_keys";

const HOTZONE_ID = "sess-focus-hotzone";

function renderToolbar(props: FocusModeToolbarProps) {
  return render(
    <I18nProvider>
      <FocusModeToolbar {...props} />
    </I18nProvider>,
  );
}

function showToolbar(): HTMLElement {
  fireEvent.mouseMove(screen.getByTestId(HOTZONE_ID));
  return screen.getByTestId(SESS_FOCUS_TOOLBAR);
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("cbrowser.locale", "en");
});

describe("FocusModeToolbar", () => {
  it("默认不渲染退出工具条", () => {
    renderToolbar({ onExit: vi.fn() });

    expect(screen.queryByTestId(SESS_FOCUS_TOOLBAR)).toBeNull();
    expect(screen.queryByTestId(SESS_FOCUS_EXIT)).toBeNull();
  });

  it("鼠标移到视口顶部热区后显示工具条", () => {
    renderToolbar({ onExit: vi.fn() });

    const toolbar = showToolbar();

    expect(toolbar).toBeInTheDocument();
    expect(screen.getByTestId(SESS_FOCUS_EXIT)).toBeInTheDocument();
  });

  it("点击退出按钮调用 onExit", () => {
    const onExit = vi.fn();
    renderToolbar({ onExit });

    showToolbar();
    fireEvent.click(screen.getByTestId(SESS_FOCUS_EXIT));

    expect(onExit).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId(SESS_FOCUS_EXIT)).toHaveAccessibleName(
      en.sessFocusExit,
    );
  });

  it("按 Escape 不退出，也不绑定任何键盘快捷键", () => {
    const onExit = vi.fn();
    renderToolbar({ onExit });

    showToolbar();
    fireEvent.keyDown(screen.getByTestId(SESS_FOCUS_TOOLBAR), {
      key: "Escape",
    });
    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.keyDown(document, { key: "c", ctrlKey: true });

    expect(onExit).not.toHaveBeenCalled();
  });

  it("工具条按钮的 mousedown 不向宿主冒泡", () => {
    const onExit = vi.fn();
    renderToolbar({ onExit });

    showToolbar();
    const listener = vi.fn();
    document.addEventListener("mousedown", listener);
    fireEvent.mouseDown(screen.getByTestId(SESS_FOCUS_EXIT));
    document.removeEventListener("mousedown", listener);

    expect(listener).not.toHaveBeenCalled();
  });
});
