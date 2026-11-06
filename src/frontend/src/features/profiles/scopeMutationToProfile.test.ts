import { describe, it, expect } from "vitest";
import type { UseMutationResult } from "@tanstack/react-query";
import { scopeMutationToProfile } from "./useProfilesQuery";

type Variables = { id: string };

function makeMutation(
  overrides: Partial<{
    isPending: boolean;
    isError: boolean;
    error: Error | null;
    variables: unknown;
  }>,
): UseMutationResult<unknown, Error, Variables> {
  return {
    isPending: false,
    isError: false,
    error: null,
    variables: undefined,
    ...overrides,
  } as unknown as UseMutationResult<unknown, Error, Variables>;
}

const targetOf = (input: Variables) => input.id;

describe("scopeMutationToProfile (isolation contract previously covered by AppLayout.isolation)", () => {
  it("does not show A's error on B", () => {
    const state = scopeMutationToProfile(
      makeMutation({
        isError: true,
        error: new Error("apply failed"),
        variables: { id: "A" },
      }),
      "B",
      targetOf,
    );
    expect(state).toEqual({ isPending: false, isError: false, error: null });
  });

  it("does not disable B while A's mutation is pending, and A's late failure stays on A", () => {
    const pending = scopeMutationToProfile(
      makeMutation({ isPending: true, variables: { id: "A" } }),
      "B",
      targetOf,
    );
    expect(pending.isPending).toBe(false);

    const lateFailure = scopeMutationToProfile(
      makeMutation({
        isError: true,
        error: new Error("late failure"),
        variables: { id: "A" },
      }),
      "A",
      targetOf,
    );
    expect(lateFailure.isError).toBe(true);
    expect(lateFailure.error?.message).toBe("late failure");
  });

  it("shows A's own state again when navigating back to A", () => {
    const state = scopeMutationToProfile(
      makeMutation({
        isPending: true,
        isError: false,
        variables: { id: "A" },
      }),
      "A",
      targetOf,
    );
    expect(state.isPending).toBe(true);
  });

  it("unwraps action-key mutation variables shaped as { input, actionKey }", () => {
    const state = scopeMutationToProfile(
      makeMutation({
        isError: true,
        error: new Error("wrapped failure"),
        variables: { input: { id: "A" }, actionKey: "key-1" },
      }),
      "A",
      targetOf,
    );
    expect(state.isError).toBe(true);
    expect(state.error?.message).toBe("wrapped failure");
  });

  it("surfaces nothing when the mutation has no target yet", () => {
    const state = scopeMutationToProfile(
      makeMutation({ isError: true, error: new Error("orphan") }),
      "A",
      targetOf,
    );
    expect(state).toEqual({ isPending: false, isError: false, error: null });
  });
});
