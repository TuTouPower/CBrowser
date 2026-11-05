import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, fireEvent, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppLayout } from "./AppLayout";

vi.mock("../features/profiles/useProfilesQuery", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../features/profiles/useProfilesQuery")>();
  return {
    // Keep pure helpers (scopeMutationToProfile, profileKeys) real; only
    // the data hooks are stubbed for this focus-contract fixture.
    ...actual,
    useProfilesQuery: () => ({ data: [], isLoading: false }),
    useProfileQuery: () => ({ data: null }),
    useProfileRuntimeQuery: () => ({ data: null }),
    useSetDesiredStateMutation: () => ({ mutate: vi.fn(), isPending: false }),
    useStopProfileMutation: () => ({ mutate: vi.fn(), isPending: false }),
    useApplyDisplaySettingsMutation: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  };
});

vi.mock("../features/auth/useAuth", () => ({
  useAuth: () => ({ logout: vi.fn() }),
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (k: string) => k, locale: "en", setLocale: vi.fn() }),
}));

describe("AppLayout iframe focus-release contract", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("blurs active iframe and refocuses window on host pointerdown", () => {
    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AppLayout />
        </MemoryRouter>
      </QueryClientProvider>
    );

    const iframe = document.createElement("iframe");
    iframe.blur = vi.fn();
    document.body.appendChild(iframe);

    // Mock document.activeElement as this iframe
    Object.defineProperty(document, "activeElement", {
      value: iframe,
      configurable: true,
    });

    const windowFocusSpy = vi.spyOn(window, "focus").mockImplementation(() => {});

    // Trigger pointerdown on host header/sidebar
    fireEvent.pointerDown(container.firstChild as HTMLElement);

    expect(iframe.blur).toHaveBeenCalled();
    expect(windowFocusSpy).toHaveBeenCalled();

    iframe.remove();
  });
});
