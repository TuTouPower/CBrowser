import { describe, it, expect, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { useBrowserSession } from "./useBrowserSession";
import { I18nProvider } from "../../i18n";
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
