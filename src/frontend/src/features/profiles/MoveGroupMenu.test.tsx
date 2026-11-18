import { describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { I18nProvider, en } from "../../i18n";
import { MoveGroupMenu } from "./MoveGroupMenu";
import type { GroupResponse } from "../../shared/api/types";

function group(id: string, name: string): GroupResponse {
  return {
    id,
    name,
    color: "slate",
    sort_order: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

const GROUPS = [
  group("g1", "Work"),
  group("g2", "Personal Projects"),
  group("g3", "Zebra Group"),
];

function renderMenu(onMove = vi.fn()) {
  render(
    <I18nProvider>
      <MoveGroupMenu groups={GROUPS} pending={false} onMove={onMove} />
    </I18nProvider>,
  );
  return { onMove };
}

function openMenu() {
  fireEvent.click(screen.getByTestId("env-batch-move"));
  return screen.findByTestId("env-move-menu");
}

describe("MoveGroupMenu (t077 AC-004/AC-005)", () => {
  it("opens anchored to the move button and picks a group on click", async () => {
    const { onMove } = renderMenu();
    await openMenu();
    expect(screen.getByTestId("env-move-group-g2")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("env-move-group-g2"));
    expect(onMove).toHaveBeenCalledTimes(1);
    expect(onMove).toHaveBeenCalledWith("g2");
    await waitFor(() =>
      expect(screen.queryByTestId("env-move-menu")).not.toBeInTheDocument(),
    );
  });

  it("filters groups by typed text and finds the last group", async () => {
    renderMenu();
    await openMenu();
    const search = screen.getByLabelText(en.searchGroups);
    fireEvent.change(search, { target: { value: "Zebra" } });
    expect(
      screen.queryByTestId("env-move-group-g1"),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("env-move-group-g3")).toBeInTheDocument();
  });

  it("Enter in the search box picks the first filtered group", async () => {
    const { onMove } = renderMenu();
    await openMenu();
    const search = screen.getByLabelText(en.searchGroups);
    fireEvent.change(search, { target: { value: "Zebra" } });
    fireEvent.keyDown(search, { key: "Enter" });
    expect(onMove).toHaveBeenCalledWith("g3");
  });

  it("ArrowDown from the search box moves focus into the list and Home/End jump", async () => {
    renderMenu();
    await openMenu();
    const search = screen.getByLabelText(en.searchGroups);
    fireEvent.keyDown(search, { key: "ArrowDown" });
    expect(document.activeElement).toBe(
      screen.getByTestId("env-move-group-g1"),
    );
    fireEvent.keyDown(document.activeElement!, { key: "End" });
    expect(document.activeElement).toBe(
      screen.getByTestId("env-move-ungrouped"),
    );
    fireEvent.keyDown(document.activeElement!, { key: "Home" });
    expect(document.activeElement).toBe(
      screen.getByTestId("env-move-group-g1"),
    );
  });

  it("Escape closes the menu and returns focus to the move button", async () => {
    renderMenu();
    await openMenu();
    const search = screen.getByLabelText(en.searchGroups);
    fireEvent.keyDown(search, { key: "Escape" });
    await waitFor(() =>
      expect(screen.queryByTestId("env-move-menu")).not.toBeInTheDocument(),
    );
    // Focus return proves the Popover trigger ref reached the button.
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByTestId("env-batch-move"),
      ),
    );
  });

  it("shows a no-match message for unknown text", async () => {
    renderMenu();
    await openMenu();
    const search = screen.getByLabelText(en.searchGroups);
    fireEvent.change(search, { target: { value: "zzz-no-such-group" } });
    expect(screen.getByText(en.noMatchingGroups)).toBeInTheDocument();
  });
});
