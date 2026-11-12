import { describe, it, expect, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { useBrowserSession } from "./useBrowserSession";
import { I18nProvider, useI18n } from "../../i18n";
import type { ApiClient } from "../../shared/api/client";
import type { RuntimeObservedState } from "./session_stage";
import type { SessionStage } from "./types";

// t058 A25: stage and error are derived from the runtimeQuery input
// (options.runtimeState). The hook no longer reads runtime itself, so
// these cases drive the stage through that input instead of a mocked
// getRuntime — the mapping itself is unchanged.
describe("useBrowserSession runtime stage mapping", () => {
  const cases: Array<[RuntimeObservedState, SessionStage]> = [
    ["error", "error"],
    ["running", "connecting_signaling"],
    ["stopping", "stopping"],
    ["stopped", "runtime_not_ready"],
    // P1-E: 首挂载 starting 直接走 connecting_signaling，不再显示错误态 + Launch。
    ["starting", "connecting_signaling"],
  ];

  for (const [observed, expectedStage] of cases) {
    it(`observed_state=${observed} -> stage ${expectedStage}`, async () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <I18nProvider>{children}</I18nProvider>
      );
      const { result } = renderHook(
        () =>
          useBrowserSession("p1", { current: null }, { runtimeState: observed }),
        { wrapper }
      );
      await waitFor(() => expect(result.current.stage).toBe(expectedStage));
    });
  }
});

describe("useBrowserSession language switching (A17)", () => {
  it("does not re-derive the stage when the language changes, and never reads runtime", async () => {
    localStorage.setItem("cbrowser.locale", "en");
    const getRuntime = vi.fn(async () => ({
      profile_id: "p1",
      display_number: 1,
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
        const session = useBrowserSession(
          "p1",
          { current: null },
          { apiClient, runtimeState: "running" },
        );
        return { ...session, setLocale };
      },
      { wrapper },
    );

    await waitFor(() => expect(result.current.stage).toBe("connecting_signaling"));
    // t058 A25: the hook never reads runtime for stage/error.
    expect(getRuntime).toHaveBeenCalledTimes(0);

    act(() => {
      result.current.setLocale("zh");
    });
    // Give any erroneous effect re-run a chance to fire.
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(getRuntime).toHaveBeenCalledTimes(0);
    expect(result.current.stage).toBe("connecting_signaling");
    localStorage.clear();
  });
});
