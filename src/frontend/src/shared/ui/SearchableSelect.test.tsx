import { beforeAll, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SearchableSelect } from "./SearchableSelect";
import type { SelectOption } from "./Select";

// The 200-option fixture renders slowly in jsdom (0.4–3.1s per test
// in isolation, longer under full-gate load) — the 5s default
// testTimeout trips on load, not on any assertion. Raise it for this
// file only; no expectation changes.
vi.setConfig({ testTimeout: 20000 });

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

const OPTIONS: SelectOption[] = Array.from({ length: 200 }, (_, i) => ({
  value: `proxy-${i}`,
  label: `Proxy${i}`,
}));

function renderSelect(props: Partial<React.ComponentProps<typeof SearchableSelect>> = {}) {
  const onValueChange = vi.fn();
  const onOptionSelect = vi.fn();
  const view = render(
    <SearchableSelect
      onValueChange={onValueChange}
      onOptionSelect={onOptionSelect}
      options={OPTIONS}
      ariaLabel="Proxy"
      searchPlaceholder="Search proxies"
      noResultsLabel="No matching proxy"
      {...props}
    />,
  );
  return { onValueChange, onOptionSelect, view };
}

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

async function openAndSearch(query: string) {
  openMenu();
  const search = await screen.findByLabelText("Search proxies");
  expect(document.activeElement).toBe(search);
  fireEvent.change(search, { target: { value: query } });
  return search;
}

describe("SearchableSelect (t077 AC-003/AC-005)", () => {
  it("filters the full candidate list by typed text and finds the last item", async () => {
    renderSelect();
    await openAndSearch("199");
    // Only Proxy199 contains "199"; the first items must be gone even
    // though they were never scrolled into view (AC-003: search finds
    // an item that was not loaded into the viewport).
    expect(
      screen.queryByRole("option", { name: "Proxy0" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Proxy199" }),
    ).toBeInTheDocument();
  });

  it("shows a no-match message for unknown text", async () => {
    renderSelect();
    await openAndSearch("zzz-no-such-proxy");
    expect(screen.getByText("No matching proxy")).toBeInTheDocument();
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
  });

  it("Enter in the search box selects the first filtered option and closes", async () => {
    const { onValueChange, onOptionSelect } = renderSelect();
    const search = await openAndSearch("199");
    fireEvent.keyDown(search, { key: "Enter" });
    expect(onValueChange).toHaveBeenCalledTimes(1);
    expect(onValueChange).toHaveBeenCalledWith("proxy-199");
    expect(onOptionSelect).toHaveBeenCalledWith("proxy-199");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("Escape closes the menu and returns focus to the trigger", async () => {
    renderSelect();
    const trigger = openMenu();
    const search = await screen.findByLabelText("Search proxies");
    fireEvent.change(search, { target: { value: "199" } });
    fireEvent.keyDown(search, { key: "Escape" });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    // Focus return runs through Radix's unmount auto-focus, which
    // settles a tick after the Escape keydown.
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("ArrowDown from the search box moves focus to the first filtered item", async () => {
    renderSelect();
    const search = await openAndSearch("19");
    fireEvent.keyDown(search, { key: "ArrowDown" });
    // Radix moves focus on a setTimeout; let it run.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(document.activeElement).toBe(
      screen.getByRole("option", { name: "Proxy19" }),
    );
  });

  it("Home/End in the search box keep focus and the caret in the search box (t077_gen_f001)", async () => {
    renderSelect();
    const search = await openAndSearch("199");
    // jsdom does not move the caret on Home/End keydown, so the
    // caret movement itself cannot be observed here; what is
    // observable is the hijack: without the fix Radix's Content
    // handler preventDefaults the key and, on a setTimeout, yanks
    // focus to the first/last option. With the fix the event is not
    // canceled, so a real browser's default caret movement proceeds
    // and focus stays in the search box.
    (search as HTMLInputElement).selectionStart = 3;
    expect(fireEvent.keyDown(search, { key: "Home" })).toBe(true);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(document.activeElement).toBe(search);
    expect((search as HTMLInputElement).selectionStart).toBe(3);
    (search as HTMLInputElement).selectionStart = 0;
    expect(fireEvent.keyDown(search, { key: "End" })).toBe(true);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(document.activeElement).toBe(search);
    expect((search as HTMLInputElement).selectionStart).toBe(0);
  });

  it("resets the search when reopened", async () => {
    renderSelect();
    const search = await openAndSearch("199");
    fireEvent.keyDown(search, { key: "Escape" });
    openMenu();
    await screen.findByLabelText("Search proxies");
    expect(
      screen.getByRole("option", { name: "Proxy0" }),
    ).toBeInTheDocument();
  });

  it("bounds the popup to the available viewport height", async () => {
    renderSelect();
    openMenu();
    const listbox = await screen.findByRole("listbox");
    expect(listbox.className).toContain("max-h-available-height");
  });

  it("records a same-value pick via onOptionSelect", async () => {
    const { onValueChange, onOptionSelect } = renderSelect({
      value: "proxy-5",
    });
    await openAndSearch("Proxy5");
    const option = screen.getByRole("option", { name: "Proxy5" });
    fireEvent.pointerDown(option, {
      pointerType: "mouse",
      button: 0,
      pointerId: 1,
    });
    fireEvent.pointerUp(option, {
      pointerType: "mouse",
      button: 0,
      pointerId: 1,
    });
    expect(onOptionSelect).toHaveBeenCalledTimes(1);
    expect(onOptionSelect).toHaveBeenCalledWith("proxy-5");
    expect(onValueChange).not.toHaveBeenCalled();
  });
});
