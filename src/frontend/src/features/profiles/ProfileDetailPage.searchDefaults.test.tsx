import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { I18nProvider } from "../../i18n";

const retryMutateAsync = vi.hoisted(() => vi.fn(async () => ({})));
const runtimeState = vi.hoisted(() => ({
  data: null as null | Record<string, unknown>,
}));

vi.mock("./useProfilesQuery", () => ({
  useProfileQuery: () => ({
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
  }),
  useProfileRuntimeQuery: () => runtimeState,
  useUpdateProfileMutation: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteProfileMutation: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useApplyDisplaySettingsMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useDuplicateProfileMutation: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useResetProfileMutation: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRetrySearchDefaultsMutation: () => ({
    mutateAsync: retryMutateAsync,
    isPending: false,
  }),
}));

import { ProfileDetailPage } from "./ProfileDetailPage";

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/profiles/p1"]}>
      <I18nProvider>
        <Routes>
          <Route path="/profiles/:profileId" element={<ProfileDetailPage />} />
        </Routes>
      </I18nProvider>
    </MemoryRouter>,
  );
}

describe("ProfileDetailPage search defaults (A55)", () => {
  it("shows an independent failure notice with a retry action", async () => {
    runtimeState.data = {
      profile_id: "p1",
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst_1",
      config_version: 1,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      updated_at: "2026-11-04T00:00:00Z",
      search_defaults: {
        state: "failed",
        error_kind: "timeout",
        runtime_instance_id: "inst_1",
        request_id: null,
        updated_at: "2026-11-04T00:00:00Z",
      },
    };
    renderPage();
    const panel = await screen.findByTestId("search-defaults-failed");
    expect(panel).toBeTruthy();
    const button = panel.querySelector("button");
    expect(button).toBeTruthy();
    fireEvent.click(button as HTMLButtonElement);
    await waitFor(() => expect(retryMutateAsync).toHaveBeenCalledWith("p1"));
  });

  it("shows no notice when search defaults applied", async () => {
    runtimeState.data = {
      profile_id: "p1",
      desired_state: "running",
      observed_state: "running",
      runtime_instance_id: "inst_1",
      config_version: 1,
      failure_count: 0,
      restart_blocked: false,
      last_exit_event_id: null,
      updated_at: "2026-11-04T00:00:00Z",
      search_defaults: {
        state: "applied",
        error_kind: null,
        runtime_instance_id: "inst_1",
        request_id: null,
        updated_at: "2026-11-04T00:00:00Z",
      },
    };
    renderPage();
    expect(screen.queryByTestId("search-defaults-failed")).toBeNull();
  });
});
