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
const APPLY_STOP_TIMEOUT_MS = 120_000;
const APPLY_START_TIMEOUT_MS = 180_000;

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
      await client.profiles.stop(id, stopOperationKey);
      await waitForRuntimeState(
        client,
        id,
        (runtime) => runtime.observed_state === "stopped",
        APPLY_STOP_TIMEOUT_MS,
      );
      await client.profiles.setDesiredState(id, "running", startOperationKey);
      return waitForRuntimeState(
        client,
        id,
        (runtime) =>
          runtime.desired_state === "running" &&
          runtime.observed_state === "running",
        APPLY_START_TIMEOUT_MS,
      );
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
