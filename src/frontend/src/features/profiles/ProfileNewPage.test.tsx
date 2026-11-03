import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "../../i18n";
import type { ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
import { ProfileNewPage } from "./ProfileNewPage";

/**
 * Real hook wiring against an injected stub client (A22): the create
 * mutation runs for real and the payload is asserted at the ApiClient
 * boundary.
 */
function makeStub() {
  return {
    profiles: {
      create: vi.fn(async () => ({ id: "p-new" })),
    },
  } as unknown as ApiClient & {
    profiles: { create: ReturnType<typeof vi.fn> };
  };
}

let stub: ReturnType<typeof makeStub>;

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ApiClientContext.Provider value={stub}>
          <MemoryRouter>
            <ProfileNewPage />
          </MemoryRouter>
        </ApiClientContext.Provider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("ProfileNewPage font bundle", () => {
  beforeEach(() => {
    localStorage.clear();
    stub = makeStub();
  });

  it("defaults to none and submits the selected bundle", async () => {
    renderPage();
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

    await waitFor(() => expect(stub.profiles.create).toHaveBeenCalledTimes(1));
    const [arg] = stub.profiles.create.mock.calls[0] as [
      { font_bundle?: string },
    ];
    expect(arg.font_bundle).toBe("wqy-zenhei");
  });
});
