import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { I18nProvider } from "../../i18n";

const createMutateAsync = vi.hoisted(() =>
  vi.fn(async () => ({ id: "p-new" })),
);

vi.mock("./useProfilesQuery", () => ({
  useCreateProfileMutation: () => ({
    mutateAsync: createMutateAsync,
    isPending: false,
  }),
}));

import { ProfileNewPage } from "./ProfileNewPage";

describe("ProfileNewPage font bundle", () => {
  it("defaults to none and submits the selected bundle", async () => {
    createMutateAsync.mockClear();
    render(
      <MemoryRouter>
        <I18nProvider>
          <ProfileNewPage />
        </I18nProvider>
      </MemoryRouter>,
    );
    const select = screen.getByTestId(
      "profile-font-bundle-select",
    ) as HTMLSelectElement;
    expect(select.value).toBe("none");
    expect(Array.from(select.options).map((o) => o.value)).toEqual([
      "none",
      "wqy-microhei",
      "wqy-zenhei",
    ]);

    fireEvent.change(screen.getByTestId("profile-name-input"), {
      target: { value: "Fonts" },
    });
    fireEvent.change(select, { target: { value: "wqy-zenhei" } });
    fireEvent.click(screen.getByTestId("profile-create-submit"));

    expect(createMutateAsync).toHaveBeenCalledTimes(1);
    const arg = createMutateAsync.mock.calls[0][0] as {
      font_bundle?: string;
    };
    expect(arg.font_bundle).toBe("wqy-zenhei");
  });
});
