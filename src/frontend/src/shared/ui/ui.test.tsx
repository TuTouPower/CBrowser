import { describe, it, expect, beforeAll, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { Button, Dialog, DropdownMenu, Popover, ToastProvider, Tooltip, useToast } from "./index";

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
