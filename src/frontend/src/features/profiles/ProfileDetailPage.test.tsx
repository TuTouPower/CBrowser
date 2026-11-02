import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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

vi.mock("./useProfilesQuery", () => ({
  useProfileQuery: () => profileState,
  useProfileRuntimeQuery: () => ({ data: null }),
  useUpdateProfileMutation: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteProfileMutation: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useApplyDisplaySettingsMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useDuplicateProfileMutation: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useResetProfileMutation: () => ({ mutateAsync: vi.fn(), isPending: false }),
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
});
