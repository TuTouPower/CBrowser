import {
  useMutation,
  type UseMutationOptions,
  type UseMutationResult,
} from "@tanstack/react-query";
import { newIdempotencyKey } from "./client";

/** Variables as seen by the wrapped mutationFn: the caller's input plus the
 * idempotency key minted for that one logical action. */
export interface ActionKeyVariables<TVariables> {
  input: TVariables;
  actionKey: string;
}

/**
 * useMutation wrapper enforcing per-action idempotency keys (A19):
 *
 * - Every mutate/mutateAsync call is one logical action and mints a fresh
 *   key at the call boundary.
 * - React Query retries re-invoke mutationFn with the same wrapped
 *   variables, so a retry of one action reuses that action's key.
 * - Concurrent calls carry distinct keys, and no settle handler clears a
 *   shared ref, so one action can never clear or reuse another's key.
 *
 * t056 A23: a caller may supply `keySource` to bind the key to something
 * longer-lived than one call — the Profile creation dialog binds its key
 * to the currently-open draft, so close/reopen resubmits reuse the same
 * key until the create succeeds.
 */
export function useActionKeyMutation<
  TData,
  TError,
  TVariables,
  TContext = unknown,
>(
  options: UseMutationOptions<
    TData,
    TError,
    ActionKeyVariables<TVariables>,
    TContext
  >,
  keyOptions?: { keySource?: () => string },
): UseMutationResult<TData, TError, TVariables, TContext> {
  const mutation = useMutation(options);
  const mintKey = keyOptions?.keySource ?? newIdempotencyKey;
  const result = {
    ...mutation,
    mutate: (
      input: TVariables,
      mutateOptions?: Parameters<typeof mutation.mutate>[1],
    ) => {
      mutation.mutate(
        { input, actionKey: mintKey() },
        mutateOptions,
      );
    },
    mutateAsync: (
      input: TVariables,
      mutateOptions?: Parameters<typeof mutation.mutateAsync>[1],
    ) => {
      return mutation.mutateAsync(
        { input, actionKey: mintKey() },
        mutateOptions,
      );
    },
  };
  return result as unknown as UseMutationResult<
    TData,
    TError,
    TVariables,
    TContext
  >;
}
