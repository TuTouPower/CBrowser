import { describe, expect, it } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { ApiError, shouldRetryRequest, type ApiClient } from "../../shared/api/client";
import { useCreateProfileMutation } from "./useProfilesQuery";

describe("mutation idempotency retry", () => {
  it("reuses one action key across React Query retries", async () => {
    const keys: string[] = [];
    let attempt = 0;
    const client = {
      profiles: {
        create: async (_data: unknown, key?: string) => {
          keys.push(key || "");
          attempt += 1;
          if (attempt === 1) {
            throw new ApiError("busy", 503, undefined, "database_busy", true);
          }
          return { id: "p1" };
        },
      },
    } as unknown as ApiClient;
    const queryClient = new QueryClient({
      defaultOptions: {
        mutations: { retry: shouldRetryRequest },
      },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useCreateProfileMutation(client), {
      wrapper,
    });
    await result.current.mutateAsync({ name: "p1" });
    await waitFor(() => expect(keys).toHaveLength(2));
    expect(keys[0]).not.toBe("");
    expect(keys[0]).toBe(keys[1]);
  });
});
