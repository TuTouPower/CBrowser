import { beforeAll, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { Select } from "./Select";

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => undefined;
  }
  // jsdom has PointerEvent but no pointer capture: Radix calls
  // hasPointerCapture on the trigger in its pointerdown handler.
  if (typeof Element.prototype.hasPointerCapture !== "function") {
    Element.prototype.hasPointerCapture = () => false;
    Element.prototype.releasePointerCapture = () => undefined;
  }
});

const OPTIONS = [
  { value: "__none__", label: "None" },
  { value: "win-1", label: "win-1" },
];

function openMenu() {
  const trigger = screen.getByRole("combobox");
  fireEvent.pointerDown(trigger, {
    pointerType: "mouse",
    button: 0,
    pointerId: 1,
  });
  fireEvent.pointerUp(trigger, {
    pointerType: "mouse",
    button: 0,
    pointerId: 1,
  });
  return trigger;
}

describe("Select onOptionSelect", () => {
  it("does not fire onOptionSelect for a drag-across release (t053_code_f006 / t053_test_f006)", async () => {
    const onOptionSelect = vi.fn();
    const onValueChange = vi.fn();
    render(
      <Select
        value="__none__"
        onValueChange={onValueChange}
        onOptionSelect={onOptionSelect}
        options={OPTIONS}
        ariaLabel="Font set"
      />,
    );
    openMenu();
    const noneOption = await screen.findByRole("option", { name: "None" });
    const winOption = await screen.findByRole("option", { name: "win-1" });

    // Press on "None", drag across, release on "win-1" without ever
    // pressing it: Radix does not commit (win-1 never saw a
    // pointerdown, so its pointerTypeRef stays "touch"), and the guard
    // must not record an explicit choice either.
    fireEvent.pointerDown(noneOption, {
      pointerType: "mouse",
      button: 0,
      pointerId: 1,
    });
    fireEvent.pointerUp(winOption, {
      pointerType: "mouse",
      button: 0,
      pointerId: 1,
    });

    expect(onOptionSelect).not.toHaveBeenCalled();
    expect(onValueChange).not.toHaveBeenCalled();
    // The menu is still open: no commit happened.
    expect(noneOption.isConnected).toBe(true);
    expect(winOption.isConnected).toBe(true);
  });

  it("fires onOptionSelect once for a same-item mouse press and release", async () => {
    const onOptionSelect = vi.fn();
    const onValueChange = vi.fn();
    render(
      <Select
        value="__none__"
        onValueChange={onValueChange}
        onOptionSelect={onOptionSelect}
        options={OPTIONS}
        ariaLabel="Font set"
      />,
    );
    openMenu();
    const winOption = await screen.findByRole("option", { name: "win-1" });

    fireEvent.pointerDown(winOption, {
      pointerType: "mouse",
      button: 0,
      pointerId: 1,
    });
    fireEvent.pointerUp(winOption, {
      pointerType: "mouse",
      button: 0,
      pointerId: 1,
    });

    expect(onOptionSelect).toHaveBeenCalledTimes(1);
    expect(onOptionSelect).toHaveBeenCalledWith("win-1");
  });

  it("touch pointerup is a no-op and the following click fires onOptionSelect exactly once (t053_test_f007)", async () => {
    const onOptionSelect = vi.fn();
    const onValueChange = vi.fn();
    render(
      <Select
        value="__none__"
        onValueChange={onValueChange}
        onOptionSelect={onOptionSelect}
        options={OPTIONS}
        ariaLabel="Font set"
      />,
    );
    openMenu();
    const noneOption = await screen.findByRole("option", { name: "None" });

    fireEvent.pointerDown(noneOption, {
      pointerType: "touch",
      button: 0,
      pointerId: 1,
    });
    fireEvent.pointerUp(noneOption, {
      pointerType: "touch",
      button: 0,
      pointerId: 1,
    });
    expect(onOptionSelect).not.toHaveBeenCalled();

    fireEvent.click(noneOption, { button: 0 });
    expect(onOptionSelect).toHaveBeenCalledTimes(1);
    expect(onOptionSelect).toHaveBeenCalledWith("__none__");
    // Same-value pick: Radix does not call onValueChange, the guard is
    // the only record of the explicit choice.
    expect(onValueChange).not.toHaveBeenCalled();
  });

  it("fires onOptionSelect once when a pointermove, not a pointerdown, brings a mouse press onto the item (p070 D case)", async () => {
    const onOptionSelect = vi.fn();
    const onValueChange = vi.fn();
    render(
      <Select
        value="__none__"
        onValueChange={onValueChange}
        onOptionSelect={onOptionSelect}
        options={OPTIONS}
        ariaLabel="Font set"
      />,
    );
    openMenu();
    const noneOption = await screen.findByRole("option", { name: "None" });
    const winOption = await screen.findByRole("option", { name: "win-1" });

    // Press starts on another item, a pointermove enters this one, and
    // the pointerup lands here. Radix sets this item's pointerTypeRef
    // to "mouse" on the move, so its pointerup commits and closes the
    // menu even though no pointerdown landed here. The guard must
    // mirror that commit rather than miss it.
    fireEvent.pointerDown(winOption, {
      pointerType: "mouse",
      button: 0,
      pointerId: 1,
    });
    fireEvent.pointerMove(noneOption, {
      pointerType: "mouse",
      button: 0,
      pointerId: 1,
    });
    fireEvent.pointerUp(noneOption, {
      pointerType: "mouse",
      button: 0,
      pointerId: 1,
    });

    expect(onOptionSelect).toHaveBeenCalledTimes(1);
    expect(onOptionSelect).toHaveBeenCalledWith("__none__");
    // Same-value commit: Radix closes the menu but does not call
    // onValueChange, so the guard is the only record of the pick.
    expect(noneOption.isConnected).toBe(false);
    expect(onValueChange).not.toHaveBeenCalled();
  });

  it("fires exactly once for a same-item press and release even when a trailing click follows", async () => {
    const onOptionSelect = vi.fn();
    const onValueChange = vi.fn();
    render(
      <Select
        value="__none__"
        onValueChange={onValueChange}
        onOptionSelect={onOptionSelect}
        options={OPTIONS}
        ariaLabel="Font set"
      />,
    );
    openMenu();
    const winOption = await screen.findByRole("option", { name: "win-1" });

    fireEvent.pointerDown(winOption, {
      pointerType: "mouse",
      button: 0,
      pointerId: 1,
    });
    fireEvent.pointerUp(winOption, {
      pointerType: "mouse",
      button: 0,
      pointerId: 1,
    });
    // A real browser dispatches a trailing click. It lands on the
    // already-unmounted item, and the `!== "mouse"` onClick guard
    // would reject it anyway. It must never add a second pick.
    fireEvent.click(winOption, { button: 0 });

    expect(onOptionSelect).toHaveBeenCalledTimes(1);
    expect(onOptionSelect).toHaveBeenCalledWith("win-1");
  });

  it("records a pick after a press leaves and re-enters the item (Radix pointermove re-arms the commit)", async () => {
    const onOptionSelect = vi.fn();
    const onValueChange = vi.fn();
    render(
      <Select
        value="__none__"
        onValueChange={onValueChange}
        onOptionSelect={onOptionSelect}
        options={OPTIONS}
        ariaLabel="Font set"
      />,
    );
    openMenu();
    const noneOption = await screen.findByRole("option", { name: "None" });
    const winOption = await screen.findByRole("option", { name: "win-1" });

    // Press "None", move onto "win-1", leave, re-enter, then release.
    // Radix's per-item ref is set by every pointermove and is not
    // cleared on pointerleave, so the re-entrant pointermove re-arms
    // "win-1" as a mouse commit and its pointerup selects it.
    fireEvent.pointerDown(noneOption, {
      pointerType: "mouse",
      button: 0,
      pointerId: 1,
    });
    fireEvent.pointerMove(winOption, {
      pointerType: "mouse",
      button: 0,
      pointerId: 1,
    });
    fireEvent.pointerLeave(winOption, {
      pointerType: "mouse",
      button: 0,
      pointerId: 1,
    });
    fireEvent.pointerMove(winOption, {
      pointerType: "mouse",
      button: 0,
      pointerId: 1,
    });
    fireEvent.pointerUp(winOption, {
      pointerType: "mouse",
      button: 0,
      pointerId: 1,
    });

    expect(onOptionSelect).toHaveBeenCalledTimes(1);
    expect(onOptionSelect).toHaveBeenCalledWith("win-1");
    // Radix committed a real value change here (not a same-value
    // confirmation), so onValueChange fires too.
    expect(onValueChange).toHaveBeenCalledTimes(1);
    expect(onValueChange).toHaveBeenCalledWith("win-1");
  });
});
