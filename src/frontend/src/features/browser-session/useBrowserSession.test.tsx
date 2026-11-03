import { describe, it, expect, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { useBrowserSession } from "./useBrowserSession";
import { I18nProvider, useI18n } from "../../i18n";
import type { ApiClient } from "../../shared/api/client";

// A31 enum finalization removed the legacy "failed"/"ready" comparisons
// from the runtime check; these cases pin the surviving stage mapping
// for every ObservedState value the API can return.
describe("useBrowserSession runtime stage mapping", () => {
  const cases: Array<[string, string]> = [
    ["error", "error"],
    ["running", "connecting_signaling"],
    ["stopping", "stopping"],
    ["stopped", "runtime_not_ready"],
    ["starting", "runtime_not_ready"],
  ];

  for (const [observed, expectedStage] of cases) {
    it(`observed_state=${observed} -> stage ${expectedStage}`, async () => {
      const apiClient = {
        profiles: {
          getRuntime: vi.fn(async () => ({
            profile_id: "p1",
            desired_state: "running",
            observed_state: observed,
          })),
        },
      } as unknown as ApiClient;
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <I18nProvider>{children}</I18nProvider>
      );
      const { result } = renderHook(
        () =>
          useBrowserSession("p1", { current: null }, { apiClient }),
        { wrapper }
      );
      await waitFor(() => expect(result.current.stage).toBe(expectedStage));
    });
  }
});

describe("useBrowserSession language switching (A17)", () => {
  it("does not re-run the runtime check or reset the stage when the language changes", async () => {
    localStorage.setItem("cbrowser.locale", "en");
    const getRuntime = vi.fn(async () => ({
      profile_id: "p1",
      desired_state: "running",
      observed_state: "running",
    }));
    const apiClient = {
      profiles: { getRuntime },
    } as unknown as ApiClient;
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <I18nProvider>{children}</I18nProvider>
    );
    const { result } = renderHook(
      () => {
        const { setLocale } = useI18n();
        const session = useBrowserSession("p1", { current: null }, { apiClient });
        return { ...session, setLocale };
      },
      { wrapper },
    );

    await waitFor(() => expect(result.current.stage).toBe("connecting_signaling"));
    expect(getRuntime).toHaveBeenCalledTimes(1);

    act(() => {
      result.current.setLocale("zh");
    });
    // Give any erroneous effect re-run a chance to fire.
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(getRuntime).toHaveBeenCalledTimes(1);
    expect(result.current.stage).toBe("connecting_signaling");
    localStorage.clear();
  });
});
