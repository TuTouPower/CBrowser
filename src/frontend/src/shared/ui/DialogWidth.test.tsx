import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Dialog } from "./Dialog";

describe("Dialog content width", () => {
  it("keeps an explicit max-width instead of the spacing-token-collapsed max-w-lg", () => {
    render(
      <Dialog trigger={<button>open</button>} title="Create" open>
        <div>body</div>
      </Dialog>,
    );
    const content = screen.getByRole("dialog");
    expect(content.className).not.toMatch(/(^|\s)max-w-lg(\s|$)/);
    expect(content.className).toContain("max-w-dialog");
  });
});
