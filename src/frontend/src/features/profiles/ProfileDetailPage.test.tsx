import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { I18nProvider } from "../../i18n";

const profileState = {
  data: {
    id: "p1",
    name: "Original",
    proxy: "",
    screen_width: 1920,
    screen_height: 1080,
    tags: [],
    current_config_version: 1,
  },
  isLoading: false,
  error: null,
};

const updateMutateAsync = vi.hoisted(() => vi.fn(async () => ({})));

vi.mock("./useProfilesQuery", () => ({
  useProfileQuery: () => profileState,
  useProfileRuntimeQuery: () => ({ data: null }),
  useUpdateProfileMutation: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
  useDeleteProfileMutation: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useApplyDisplaySettingsMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useDuplicateProfileMutation: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useResetProfileMutation: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRetrySearchDefaultsMutation: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import { ProfileDetailPage } from "./ProfileDetailPage";

describe("ProfileDetailPage", () => {
  it("does not overwrite unsaved edits when background data refreshes", () => {
    const view = render(
      <MemoryRouter initialEntries={["/profiles/p1"]}>
        <I18nProvider>
          <ProfileDetailPage />
        </I18nProvider>
      </MemoryRouter>,
    );
    const input = screen.getByTestId("profile-name-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Edited locally" } });
    profileState.data = { ...profileState.data, name: "Server refreshed" };
    view.rerender(
      <MemoryRouter initialEntries={["/profiles/p1"]}>
        <I18nProvider>
          <ProfileDetailPage />
        </I18nProvider>
      </MemoryRouter>,
    );
    expect((screen.getByTestId("profile-name-input") as HTMLInputElement).value).toBe(
      "Edited locally",
    );
  });

  it("echoes the saved font bundle and submits a changed one", async () => {
    updateMutateAsync.mockClear();
    profileState.data = {
      ...profileState.data,
      name: "Original",
      font_bundle: "wqy-zenhei",
    } as typeof profileState.data;
    // Fresh JSX per render: reusing one element object makes React bail
    // out on rerender, which would leave the echo assertion below vacuous.
    const pageTree = () => (
      <MemoryRouter initialEntries={["/profiles/p1"]}>
        <I18nProvider>
          <Routes>
            <Route path="/profiles/:profileId" element={<ProfileDetailPage />} />
          </Routes>
        </I18nProvider>
      </MemoryRouter>
    );
    const view = render(pageTree());
    const select = screen.getByTestId(
      "profile-font-bundle-select",
    ) as HTMLSelectElement;
    expect(select.value).toBe("wqy-zenhei");
    expect(Array.from(select.options).map((o) => o.value)).toEqual([
      "none",
      "wqy-microhei",
      "wqy-zenhei",
    ]);

    fireEvent.change(select, { target: { value: "wqy-microhei" } });
    fireEvent.submit(select.closest("form") as HTMLFormElement);
    expect(updateMutateAsync).toHaveBeenCalledTimes(1);
    const arg = updateMutateAsync.mock.calls[0][0] as {
      data: { font_bundle?: string };
    };
    expect(arg.data.font_bundle).toBe("wqy-microhei");

    // After the save resolves, the server echo (refetched profile) drives
    // the select: rerendering with the API-returned value keeps it shown.
    await new Promise((resolve) => setTimeout(resolve, 0));
    profileState.data = {
      ...profileState.data,
      font_bundle: "wqy-microhei",
    } as typeof profileState.data;
    view.rerender(pageTree());
    expect(
      (screen.getByTestId("profile-font-bundle-select") as HTMLSelectElement)
        .value,
    ).toBe("wqy-microhei");
  });
});
