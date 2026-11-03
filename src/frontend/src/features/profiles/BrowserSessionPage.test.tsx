import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { I18nProvider } from "../../i18n";
import { BrowserSessionPage } from "./BrowserSessionPage";

vi.mock("./useProfilesQuery", () => ({
  useProfileQuery: () => ({
    data: {
      id: "p1",
      name: "Profile One",
      clipboard_sync: true,
      tags: [],
    },
    isLoading: false,
  }),
  useProfileRuntimeQuery: () => ({
    data: {
      observed_state: "stopped",
      desired_state: "stopped",
      last_coordinator_error: null,
    },
    isLoading: false,
  }),
  useSetDesiredStateMutation: () => ({
    mutate: vi.fn(),
    isPending: false,
    isError: true,
    error: new Error("container start failed"),
  }),
}));

describe("BrowserSessionPage", () => {
  it("shows a start error instead of swallowing the mutation failure", () => {
    render(
      <MemoryRouter initialEntries={["/?profileId=p1"]}>
        <I18nProvider>
          <BrowserSessionPage />
        </I18nProvider>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("session-start-error").textContent).toContain(
      "container start failed",
    );
  });
});
