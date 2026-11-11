import { describe, expect, it, vi, beforeAll } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { I18nProvider, en } from "../../i18n";
import { TimezoneCombobox } from "./TimezoneCombobox";
import { getTimezones } from "./profile_locale";

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => undefined;
  }
});

function renderCombobox(
  value: string | null = null,
  onValueChange = vi.fn(),
) {
  return {
    onValueChange,
    view: render(
      <I18nProvider>
        <TimezoneCombobox
          value={value}
          onValueChange={onValueChange}
          ariaLabel={en.formTimezone}
          testId="tz-combobox"
        />
      </I18nProvider>,
    ),
  };
}

describe("TimezoneCombobox (t053 AC-003)", () => {
  it("filters by typed text and selects the match", async () => {
    const { onValueChange } = renderCombobox();
    const input = screen.getByTestId("tz-combobox");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "Shang" } });

    const listbox = screen.getByTestId("tz-combobox-listbox");
    expect(listbox.textContent).toContain("Asia/Shanghai");
    expect(listbox.textContent).not.toContain("Europe/London");

    fireEvent.keyDown(input, { key: "Enter" });
    expect(onValueChange).toHaveBeenCalledWith("Asia/Shanghai");
  });

  it("opens to the full scrollable IANA list when nothing is typed", async () => {
    renderCombobox();
    const input = screen.getByTestId("tz-combobox");
    fireEvent.focus(input);

    const listbox = screen.getByTestId("tz-combobox-listbox");
    expect(listbox.className).toContain("overflow-y-auto");
    const options = screen.getAllByRole("option");
    // Auto + every IANA timezone.
    expect(options.length).toBe(getTimezones().length + 1);
    expect(listbox.textContent).toContain("Asia/Shanghai");
    expect(listbox.textContent).toContain("Europe/London");
    expect(listbox.textContent).toContain("America/New_York");
  });

  it("pins common timezones first", async () => {
    renderCombobox();
    fireEvent.focus(screen.getByTestId("tz-combobox"));
    const options = screen.getAllByRole("option");
    expect(options[1]?.textContent).toBe("Asia/Shanghai");
  });

  it("resets the highlight to the first match when the candidate set changes without changing size", async () => {
    const { onValueChange } = renderCombobox();
    const input = screen.getByTestId("tz-combobox");
    fireEvent.focus(input);
    // "new" and "par" both match exactly two zones, so the list size
    // stays 2 while its content changes.
    fireEvent.change(input, { target: { value: "new" } });
    expect(screen.getAllByRole("option")).toHaveLength(2);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(screen.getAllByRole("option")[1]).toHaveAttribute(
      "aria-selected",
      "true",
    );
    fireEvent.change(input, { target: { value: "par" } });
    expect(screen.getAllByRole("option")).toHaveLength(2);
    // The highlight must return to the first match, not stay on the
    // second row of the new list.
    expect(screen.getAllByRole("option")[0]).toHaveAttribute(
      "aria-selected",
      "true",
    );
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onValueChange).toHaveBeenCalledWith("Europe/Paris");
  });

  it("selects with the keyboard (arrow keys + Enter)", async () => {
    const { onValueChange } = renderCombobox();
    const input = screen.getByTestId("tz-combobox");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "Europe/Lond" } });
    // First option is Europe/London; move down and back up stays on it.
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "ArrowUp" });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onValueChange).toHaveBeenCalledWith("Europe/London");
  });

  it("offers the auto option and selects it", async () => {
    const { onValueChange } = renderCombobox("Asia/Shanghai");
    const input = screen.getByTestId("tz-combobox");
    expect(input).toHaveValue("Asia/Shanghai");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "" } });
    // Options commit on mousedown (before blur), like a real pointer pick.
    fireEvent.mouseDown(
      screen.getByTestId("tz-combobox-option-__auto__"),
    );
    expect(onValueChange).toHaveBeenCalledWith(null);
  });

  it("shows a no-match message for unknown text", async () => {
    renderCombobox();
    const input = screen.getByTestId("tz-combobox");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "Mars/Olympus" } });
    expect(screen.getByText(en.formTimezoneNoMatch)).toBeInTheDocument();
  });
});
