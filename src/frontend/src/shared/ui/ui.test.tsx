import { describe, it, expect, beforeAll, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import {
  Button,
  Dialog,
  DropdownMenu,
  IconButton,
  Popover,
  RegionBadge,
  SearchField,
  StatusBadge,
  ToastProvider,
  Tooltip,
  useToast,
} from "./index";

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
        static fromRect() {
          return new DOMRect();
        }
      },
    );
  }
});

describe("Dialog", () => {
  it("exposes dialog role, traps focus, closes on Esc and restores focus", async () => {
    render(
      <Dialog trigger={<Button variant="primary">Open</Button>} title="Settings">
        <button type="button">Inside action</button>
      </Dialog>,
    );
    const trigger = screen.getByRole("button", { name: "Open" });
    fireEvent.click(trigger);

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(within(dialog).getByText("Settings")).toBeInTheDocument();
    expect(dialog.contains(document.activeElement)).toBe(true);

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(document.activeElement).toBe(trigger);
  });
});

describe("DropdownMenu", () => {
  it("exposes menu roles and closes on Esc", async () => {
    render(
      <DropdownMenu
        ariaLabel="Actions"
        trigger={<Button>Open menu</Button>}
        items={[{ label: "Rename" }, { label: "Delete" }]}
      />,
    );
    const trigger = screen.getByRole("button", { name: "Open menu" });
    fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false });
    const menu = await screen.findByRole("menu");
    expect(within(menu).getAllByRole("menuitem")).toHaveLength(2);
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
  });
});

describe("Popover", () => {
  it("exposes dialog role and closes on Esc", async () => {
    render(
      <Popover ariaLabel="Details" trigger={<Button>Open popover</Button>}>
        <div>Popover body</div>
      </Popover>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open popover" }));
    const panel = await screen.findByRole("dialog");
    expect(within(panel).getByText("Popover body")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("Tooltip", () => {
  it("exposes tooltip role on focus", async () => {
    render(
      <Tooltip content="More info">
        <Button>Info</Button>
      </Tooltip>,
    );
    const trigger = screen.getByRole("button", { name: "Info" });
    fireEvent.focus(trigger);
    expect(await screen.findByRole("tooltip")).toHaveTextContent("More info");
  });
});

function ToastProbe() {
  const { show } = useToast();
  return (
    <div>
      <button type="button" onClick={() => show("first")}>first</button>
      <button type="button" onClick={() => show("second")}>second</button>
    </div>
  );
}

describe("Toast", () => {
  it("keeps exactly one global viewport instance", async () => {
    render(
      <ToastProvider>
        <ToastProbe />
      </ToastProvider>,
    );
    expect(screen.getAllByTestId("toast-viewport")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "first" }));
    expect(await screen.findByTestId("toast-item")).toHaveTextContent("first");
    fireEvent.click(screen.getByRole("button", { name: "second" }));
    await waitFor(() => expect(screen.getByTestId("toast-item")).toHaveTextContent("second"));
    expect(screen.getAllByTestId("toast-viewport")).toHaveLength(1);
    expect(screen.getAllByTestId("toast-item")).toHaveLength(1);
  });
});

// t073 AC-001/002/005/006: Flex 搜索框、彩色状态徽标、危险图标按钮与尺寸弹窗。
describe("t073 UI primitives", () => {
  it("SearchField 用 Flex 组合根除图标文字重叠，data-testid 落在 input", () => {
    render(
      <SearchField
        label="Search"
        data-testid="env-search"
        placeholder="Find"
        containerClassName="w-(--component-search-field-width)"
      />,
    );
    const input = screen.getByTestId("env-search") as HTMLInputElement;
    expect(input.tagName).toBe("INPUT");
    expect(input).toHaveAttribute("aria-label", "Search");
    expect(input).toHaveAttribute("placeholder", "Find");
    const container = input.parentElement as HTMLElement;
    expect(container.className).toContain("flex");
    expect(container.className).toContain("items-center");
    expect(container.className).not.toContain("relative");
    expect(container.className).not.toContain("pl-xl");
    // t073_gen_f002: 基础类不得含 w-full，否则纯 join 的 cn() 会覆盖容器宽度约束。
    expect(container.className).not.toContain("w-full");
    expect(container.className).toContain("w-(--component-search-field-width)");
    const icon = container.querySelector("svg");
    expect(icon).not.toBeNull();
    expect(icon?.getAttribute("class") ?? "").toContain("shrink-0");
    expect(icon?.getAttribute("class") ?? "").not.toContain("absolute");
  });

  it.each([
    ["running", "bg-success-soft", "text-success", "border-success"],
    ["transition", "bg-warning-soft", "text-warning", "border-warning"],
    ["error", "bg-danger-soft", "text-danger", "border-danger"],
  ] as const)(
    "StatusBadge %s 使用彩色语义文字与描边，不再用 accent-soft/on-surface",
    (tone, background, foreground, border) => {
      render(<StatusBadge tone={tone} label="state" />);
      const badge = screen.getByText("state");
      expect(badge.className).toContain(background);
      expect(badge.className).toContain(foreground);
      expect(badge.className).toContain(border);
      expect(badge.className).not.toContain("bg-accent-soft");
      expect(badge.className).not.toContain("text-on-surface");
    },
  );

  it("IconButton danger/warning 变体使用语义色", () => {
    const { rerender } = render(
      <IconButton label="del" variant="danger">x</IconButton>,
    );
    expect(screen.getByRole("button", { name: "del" }).className).toContain(
      "text-danger",
    );
    rerender(<IconButton label="stop" variant="warning">x</IconButton>);
    expect(screen.getByRole("button", { name: "stop" }).className).toContain(
      "text-warning",
    );
  });

  it.each([
    ["sm", "max-w-dialog-sm"],
    ["md", "max-w-dialog"],
    ["lg", "max-w-dialog-lg"],
    ["xl", "max-w-dialog-xl"],
  ] as const)("Dialog size=%s 映射语义容器类并支持内部滚动", async (size, cls) => {
    render(
      <Dialog trigger={<Button>Open</Button>} title="T" size={size}>
        <div>body</div>
      </Dialog>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog.className.split(/\s+/)).toContain(cls);
    expect(dialog.className).toContain("max-h-dialog-height");
    expect(dialog.className).toContain("flex-col");
    expect(dialog.querySelector(".overflow-y-auto")).not.toBeNull();
  });
});

describe("RegionBadge (t079 AC-005)", () => {
  it("renders flag + name for a known region", () => {
    render(
      <RegionBadge code="US" name="United States" unknownLabel="Unknown region" />,
    );
    expect(screen.getByText("United States")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "United States" })).toHaveTextContent("🇺🇸");
  });

  it("renders the placeholder, never a fabricated flag, for unassigned codes", () => {
    render(<RegionBadge code="XX" unknownLabel="Unknown region" />);
    expect(screen.getByRole("img", { name: "Unknown region" })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("🇽🇽");
  });
});
