import { useEffect, useRef } from "react";
import {
  useQuery,
  useMutation,
  useQueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";
import { defaultApiClient, ApiClient, newIdempotencyKey } from "../../shared/api/client";
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
  const actionKey = useRef<string | null>(null);
  return useMutation({
    mutationFn: (data: ProfileCreateRequest) =>
      client.profiles.create(data, (actionKey.current ??= newIdempotencyKey())),
    onSettled: () => {
      actionKey.current = null;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: profileKeys.lists() });
    },
  });
}

export function useUpdateProfileMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileResponse, Error, { id: string; data: ProfileUpdateRequest }> {
  const queryClient = useQueryClient();
  const actionKey = useRef<string | null>(null);
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ProfileUpdateRequest }) =>
      client.profiles.update(id, data, (actionKey.current ??= newIdempotencyKey())),
    onSettled: () => {
      actionKey.current = null;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: profileKeys.lists() });
      queryClient.invalidateQueries({ queryKey: profileKeys.detail(variables.id) });
      queryClient.invalidateQueries({ queryKey: profileKeys.runtime(variables.id) });
    },
  });
}

export function useDeleteProfileMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  const actionKey = useRef<string | null>(null);
  return useMutation({
    mutationFn: (id: string) =>
      client.profiles.delete(id, (actionKey.current ??= newIdempotencyKey())),
    onSettled: () => {
      actionKey.current = null;
    },
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
  const actionKey = useRef<string | null>(null);
  return useMutation({
    mutationFn: ({ id, includeBrowserState, name }) =>
      client.profiles.duplicate(
        id,
        { include_browser_state: includeBrowserState, name },
        (actionKey.current ??= newIdempotencyKey()),
      ),
    onSettled: () => {
      actionKey.current = null;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: profileKeys.lists() });
    },
  });
}

export function useResetProfileMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileResponse, Error, string> {
  const queryClient = useQueryClient();
  const actionKey = useRef<string | null>(null);
  return useMutation({
    mutationFn: (id: string) =>
      client.profiles.reset(id, (actionKey.current ??= newIdempotencyKey())),
    onSettled: () => {
      actionKey.current = null;
    },
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
  const actionKey = useRef<string | null>(null);
  return useMutation({
    mutationFn: ({ id, state }: { id: string; state: "running" | "stopped" }) =>
      client.profiles.setDesiredState(
        id,
        state,
        (actionKey.current ??= newIdempotencyKey()),
      ),
    onSettled: () => {
      actionKey.current = null;
    },
    onSuccess: (data, variables) => {
      queryClient.setQueryData(profileKeys.runtime(variables.id), data);
      queryClient.invalidateQueries({ queryKey: profileKeys.lists() });
    },
  });
}

export function useRetrySearchDefaultsMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileRuntimeResponse, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.profiles.retrySearchDefaults(id),
    onSuccess: (data, id) => {
      queryClient.setQueryData(profileKeys.runtime(id), data);
    },
  });
}

export function useStopProfileMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileRuntimeResponse, Error, string> {
  const queryClient = useQueryClient();
  const actionKey = useRef<string | null>(null);
  return useMutation({
    mutationFn: (id: string) =>
      client.profiles.stop(id, (actionKey.current ??= newIdempotencyKey())),
    onSettled: () => {
      actionKey.current = null;
    },
    onSuccess: (data, id) => {
      queryClient.setQueryData(profileKeys.runtime(id), data);
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
  const stopKey = useRef<string | null>(null);
  const startKey = useRef<string | null>(null);
  return useMutation({
    mutationFn: async (id: string) => {
      const stopOperationKey = (stopKey.current ??= newIdempotencyKey());
      const startOperationKey = (startKey.current ??= newIdempotencyKey());
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
    onSettled: () => {
      stopKey.current = null;
      startKey.current = null;
    },
    onSuccess: (data, id) => {
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
