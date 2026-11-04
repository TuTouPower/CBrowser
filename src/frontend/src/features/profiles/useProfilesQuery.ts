import { useEffect } from "react";
import {
  useQuery,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";
import { defaultApiClient, ApiClient } from "../../shared/api/client";
import { useActionKeyMutation } from "../../shared/api/action_key_mutation";
import type {
  ProfileControlStateData,
  ProfileResponse,
  ProfileCreateRequest,
  ProfileUpdateRequest,
  ProfileRuntimeResponse,
} from "../../shared/api/types";
import { ProfileEventsClient } from "../../shared/api/sse";

export const profileKeys = {
  all: ["profiles"] as const,
  lists: () => [...profileKeys.all, "list"] as const,
  detail: (id: string) => [...profileKeys.all, "detail", id] as const,
  runtime: (id: string) => [...profileKeys.all, "runtime", id] as const,
};

export function useProfilesQuery(
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProfileResponse[], Error> {
  return useQuery({
    queryKey: profileKeys.lists(),
    queryFn: () => client.profiles.list(),
  });
}

export function useProfileQuery(
  profileId: string | null | undefined,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProfileResponse, Error> {
  return useQuery({
    queryKey: profileKeys.detail(profileId || ""),
    queryFn: () => client.profiles.get(profileId!),
    enabled: Boolean(profileId),
  });
}

export function useProfileRuntimeQuery(
  profileId: string | null | undefined,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProfileRuntimeResponse, Error> {
  return useQuery({
    queryKey: profileKeys.runtime(profileId || ""),
    queryFn: () => client.profiles.getRuntime(profileId!),
    enabled: Boolean(profileId),
  });
}

export function useCreateProfileMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileResponse, Error, ProfileCreateRequest> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.create(input, actionKey),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: profileKeys.lists() });
    },
  });
}

export function useUpdateProfileMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileResponse, Error, { id: string; data: ProfileUpdateRequest }> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.update(input.id, input.data, actionKey),
    onSuccess: (_data, { input }) => {
      queryClient.invalidateQueries({ queryKey: profileKeys.lists() });
      queryClient.invalidateQueries({ queryKey: profileKeys.detail(input.id) });
      queryClient.invalidateQueries({ queryKey: profileKeys.runtime(input.id) });
    },
  });
}

export function useDeleteProfileMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.delete(input, actionKey),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: profileKeys.lists() });
    },
  });
}

export function useDuplicateProfileMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<
  ProfileResponse,
  Error,
  { id: string; includeBrowserState: boolean; name?: string }
> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.duplicate(
        input.id,
        { include_browser_state: input.includeBrowserState, name: input.name },
        actionKey,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: profileKeys.lists() });
    },
  });
}

export function useResetProfileMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileResponse, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.reset(input, actionKey),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: profileKeys.lists() });
      queryClient.invalidateQueries({ queryKey: profileKeys.detail(data.id) });
      queryClient.invalidateQueries({ queryKey: profileKeys.runtime(data.id) });
    },
  });
}

export interface ProfileScopedMutationState {
  isPending: boolean;
  isError: boolean;
  error: Error | null;
}

/**
 * Scopes a shared mutation hook's visible state to one Profile.
 *
 * Components such as AppLayout stay mounted across Profile switches, so
 * the raw mutation result would show Profile A's error (and pending
 * disablement) while the user is looking at Profile B, and A's late
 * settle would repaint B's view. The mutation's target is read from its
 * variables — for action-key mutations the wrapped `{ input, actionKey }`
 * shape is unwrapped — and state is only surfaced when the target is the
 * Profile currently on screen. Mutation side effects (query cache
 * writes) are already keyed by the target id and are unaffected.
 */
export function scopeMutationToProfile<TData, TVariables>(
  mutation: UseMutationResult<TData, Error, TVariables>,
  profileId: string | null | undefined,
  targetOf: (input: TVariables) => string | null | undefined,
): ProfileScopedMutationState {
  const rawVariables = (mutation as { variables?: unknown }).variables;
  const input =
    rawVariables && typeof rawVariables === "object" && "input" in rawVariables
      ? (rawVariables as { input: TVariables }).input
      : (rawVariables as TVariables | undefined);
  const target = input != null ? targetOf(input) : undefined;
  const matches = target != null && profileId != null && target === profileId;
  return {
    isPending: matches && mutation.isPending,
    isError: matches && mutation.isError,
    error: matches ? mutation.error : null,
  };
}

export function useSetDesiredStateMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<
  ProfileRuntimeResponse,
  Error,
  { id: string; state: "running" | "stopped" }
> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.setDesiredState(input.id, input.state, actionKey),
    onSuccess: (data, { input }) => {
      queryClient.setQueryData(profileKeys.runtime(input.id), data);
      queryClient.invalidateQueries({ queryKey: profileKeys.lists() });
    },
  });
}

export function useRetrySearchDefaultsMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileRuntimeResponse, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.retrySearchDefaults(input, actionKey),
    onSuccess: (data, { input }) => {
      queryClient.setQueryData(profileKeys.runtime(input), data);
    },
  });
}

export function useRestoreControlMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileControlStateData, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.restoreControl(input, actionKey),
    onSuccess: (data, { input }) => {
      // The restore endpoint returns only the control state; merge it
      // into the cached runtime response (SSE will confirm it next).
      queryClient.setQueryData(
        profileKeys.runtime(input),
        (old: ProfileRuntimeResponse | undefined) => {
          if (!old) return old;
          return { ...old, control: data };
        },
      );
      queryClient.invalidateQueries({ queryKey: profileKeys.runtime(input) });
    },
  });
}

export function useStopProfileMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileRuntimeResponse, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.stop(input, actionKey),
    onSuccess: (data, { input }) => {
      queryClient.setQueryData(profileKeys.runtime(input), data);
      queryClient.invalidateQueries({ queryKey: profileKeys.lists() });
    },
  });
}

const APPLY_POLL_INTERVAL_MS = 500;
const APPLY_PROBE_TIMEOUT_MS = 30_000;
const APPLY_STOP_TIMEOUT_MS = 120_000;
const APPLY_START_TIMEOUT_MS = 180_000;

/**
 * Stage record for one apply action, keyed by its action key so React
 * Query retries of the same logical action resume where the previous
 * attempt left off. Entries are removed when the action converges; a
 * permanently failed action leaves one small entry behind, bounded by
 * the number of failed actions in the page session.
 */
interface ApplyStage {
  /** Whether the pre-action runtime has been observed at least once. */
  observed: boolean;
  /** runtime_instance_id seen before this action's stop step. */
  preStopInstanceId: string | null;
  /** setDesiredState("running") has been invoked for this action. */
  startRequested: boolean;
}

const applyStages = new Map<string, ApplyStage>();

function getApplyStage(actionKey: string): ApplyStage {
  let stage = applyStages.get(actionKey);
  if (!stage) {
    stage = { observed: false, preStopInstanceId: null, startRequested: false };
    applyStages.set(actionKey, stage);
  }
  return stage;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function waitForRuntimeState(
  client: ApiClient,
  profileId: string,
  predicate: (runtime: ProfileRuntimeResponse) => boolean,
  timeoutMs: number,
): Promise<ProfileRuntimeResponse> {
  const deadline = Date.now() + timeoutMs;
  let last: ProfileRuntimeResponse | null = null;
  let consecutiveFailures = 0;
  while (Date.now() < deadline) {
    try {
      last = await client.profiles.getRuntime(profileId);
      consecutiveFailures = 0;
      if (predicate(last)) {
        return last;
      }
    } catch (err) {
      consecutiveFailures += 1;
      if (consecutiveFailures >= 3) {
        throw new Error(
          `Runtime polling failed: ${err instanceof Error ? err.message : String(err)}`,
        );
      }
    }
    await sleep(APPLY_POLL_INTERVAL_MS);
  }
  throw new Error(`Profile runtime did not converge before timeout: ${JSON.stringify(last)}`);
}

export function useApplyDisplaySettingsMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileRuntimeResponse, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: async ({ input: id, actionKey }) => {
      // One apply call is one logical action; its stop and start steps are
      // distinct backend operations, so each derives its own stable key
      // from the action key. A retry of the whole action reuses both.
      const stopOperationKey = `${actionKey}:stop`;
      const startOperationKey = `${actionKey}:start`;
      const stage = getApplyStage(actionKey);

      // Resume from observation, not from the top: a retry first looks at
      // where the previous attempt actually left the runtime. Replaying
      // the stop step is not harmless — the server replays an already
      // applied stop key as a no-op, so the new instance would never be
      // stopped and a wait for "stopped" could only time out (p018).
      // The probe is bounded by the polling helper (three consecutive
      // query failures or the probe deadline produce an error).
      const current = await waitForRuntimeState(
        client,
        id,
        () => true,
        APPLY_PROBE_TIMEOUT_MS,
      );
      if (!stage.observed) {
        stage.observed = true;
        stage.preStopInstanceId = current.runtime_instance_id ?? null;
      }

      // The start step already took effect on the server but its response
      // was lost: the runtime is converging back to running. Skip both
      // sends and converge on running; never stop or rebuild the new
      // instance. "Already effective" needs evidence that the running
      // instance is the one this action started: when both the pre-stop
      // instance id and the current instance id are known they must
      // differ — desired/observed alone cannot distinguish a genuinely
      // new instance from the pre-stop instance restored by an external
      // actor. When either id is unknown, fall back to the
      // desired/observed heuristic.
      const currentInstanceId = current.runtime_instance_id ?? null;
      const instanceEvidence =
        stage.preStopInstanceId === null ||
        currentInstanceId === null ||
        currentInstanceId !== stage.preStopInstanceId;
      const startAlreadyEffective =
        stage.startRequested &&
        instanceEvidence &&
        current.desired_state === "running" &&
        (current.observed_state === "running" ||
          current.observed_state === "starting");

      if (!startAlreadyEffective) {
        if (current.observed_state !== "stopped") {
          await client.profiles.stop(id, stopOperationKey);
          await waitForRuntimeState(
            client,
            id,
            (runtime) => runtime.observed_state === "stopped",
            APPLY_STOP_TIMEOUT_MS,
          );
        }
        // Record the intent before the call: if the response is lost,
        // the retry distinguishes "start applied" from "never sent" by
        // observing the runtime state (see startAlreadyEffective).
        stage.startRequested = true;
        await client.profiles.setDesiredState(id, "running", startOperationKey);
      }
      const final = await waitForRuntimeState(
        client,
        id,
        (runtime) =>
          runtime.desired_state === "running" &&
          runtime.observed_state === "running",
        APPLY_START_TIMEOUT_MS,
      );
      applyStages.delete(actionKey);
      return final;
    },
    onSuccess: (data, { input: id }) => {
      queryClient.setQueryData(profileKeys.runtime(id), data);
      queryClient.invalidateQueries({ queryKey: profileKeys.lists() });
      queryClient.invalidateQueries({ queryKey: profileKeys.detail(id) });
    },
  });
}

export function useProfileEventsSync(sseClient: ProfileEventsClient): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    const unsubscribe = sseClient.onEvent((event) => {
      queryClient.setQueryData(
        profileKeys.runtime(event.profile_id),
        (old: ProfileRuntimeResponse | undefined) => {
          // Events carry no config_version: never synthesize a runtime entry.
          if (!old) return undefined;
          return {
            ...old,
            desired_state: event.desired_state ?? old.desired_state,
            observed_state: event.observed_state ?? old.observed_state,
            runtime_instance_id:
              event.runtime_instance_id !== undefined
                ? event.runtime_instance_id
                : old.runtime_instance_id,
            failure_count: event.failure_count ?? old.failure_count,
            restart_blocked: event.restart_blocked ?? old.restart_blocked,
            last_coordinator_error:
              event.last_coordinator_error !== undefined
                ? event.last_coordinator_error
                : old.last_coordinator_error,
            search_defaults:
              event.search_defaults !== undefined
                ? event.search_defaults
                : old.search_defaults,
            transport:
              event.transport !== undefined
                ? event.transport
                : old.transport,
            control:
              // t031 (review f006): SSE is normally ordered, but a
              // delayed or replayed event must not overwrite newer
              // generation state: only apply control at or above the
              // cached generation.
              event.control != null &&
              (old.control == null ||
                event.control.generation >= old.control.generation)
                ? event.control
                : old.control,
            updated_at: event.updated_at ?? old.updated_at,
          };
        },
      );
      queryClient.invalidateQueries({ queryKey: profileKeys.runtime(event.profile_id) });
      queryClient.invalidateQueries({ queryKey: profileKeys.lists() });
    });

    sseClient.start();

    return () => {
      unsubscribe();
      sseClient.stop();
    };
  }, [sseClient, queryClient]);
}
