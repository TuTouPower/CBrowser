import { describe, expect, it } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import type { ApiClient } from "../../shared/api/client";
import {
  useDeleteArtifactMutation,
  useUploadArtifactMutation,
} from "./useArtifacts";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function makeWrapper(queryClient: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("artifact per-action idempotency keys (A19)", () => {
  it("concurrent uploads of different files use different keys", async () => {
    const seen: { name: string; key: string }[] = [];
    const gate = deferred<unknown>();
    const client = {
      artifacts: {
        upload: (_profileId: string, file: File, key?: string) => {
          seen.push({ name: file.name, key: key || "" });
          return gate.promise;
        },
      },
    } as unknown as ApiClient;
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    const { result } = renderHook(() => useUploadArtifactMutation("p1", client), {
      wrapper: makeWrapper(queryClient),
    });

    act(() => {
      result.current.mutate(new File(["a"], "a.txt"));
      result.current.mutate(new File(["b"], "b.txt"));
    });
    await waitFor(() => expect(seen).toHaveLength(2));
    expect(seen[0]?.key).not.toBe("");
    expect(seen[1]?.key).not.toBe("");
    expect(seen[0]?.key).not.toBe(seen[1]?.key);
    gate.resolve({});
  });

  it("concurrent deletes of different artifacts use different keys", async () => {
    const seen: { id: string; key: string }[] = [];
    const gate = deferred<void>();
    const client = {
      artifacts: {
        delete: (_profileId: string, artifactId: string, key?: string) => {
          seen.push({ id: artifactId, key: key || "" });
          return gate.promise;
        },
      },
    } as unknown as ApiClient;
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    const { result } = renderHook(() => useDeleteArtifactMutation("p1", client), {
      wrapper: makeWrapper(queryClient),
    });

    act(() => {
      result.current.mutate("a1");
      result.current.mutate("a2");
    });
    await waitFor(() => expect(seen).toHaveLength(2));
    expect(seen[0]?.key).not.toBe(seen[1]?.key);
    gate.resolve(undefined);
  });
});
