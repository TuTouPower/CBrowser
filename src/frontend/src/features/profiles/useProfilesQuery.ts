import { useEffect } from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
  type UseQueryResult,
  type UseMutationResult,
} from "@tanstack/react-query";
import { defaultApiClient, ApiClient } from "../../shared/api/client";
import { useActionKeyMutation } from "../../shared/api/action_key_mutation";
import type {
  CandidateEntry,
  ProfileCollectionPage,
  ProfileControlStateData,
  ProfileDeletionBatchResponse,
  ProfileDeletionOperation,
  ProfileResponse,
  ProfileCreateRequest,
  ProfileUpdateRequest,
  ProfileRuntimeResponse,
  ProxyCollectionPage,
  ProxyCandidateEntry,
  ProxyCountryRange,
  ProxyUsedByResponse,
  ProxyProbeJob,
  ProxyProbeJobAccepted,
  ProxyProbeJobMember,
  ProxyProbeJobRequest,
  RuntimeSummaryResponse,
  RuntimeSummaryEntry,
  GroupResponse,
  GroupCreateRequest,
  GroupUpdateRequest,
  ProxyResponse,
  ProxyCreateRequest,
  ProxyUpdateRequest,
  FontSetListResponse,
} from "../../shared/api/types";
import { ProfileEventsClient } from "../../shared/api/sse";

export const profileKeys = {
  all: ["profiles"] as const,
  lists: () => [...profileKeys.all, "list"] as const,
  detail: (id: string) => [...profileKeys.all, "detail", id] as const,
  runtime: (id: string) => [...profileKeys.all, "runtime", id] as const,
  runtimeSummary: () => [...profileKeys.all, "runtime-summary"] as const,
  collection: (params: object) =>
    [...profileKeys.all, "collection", params] as const,
  /** t076 review f003: prefix covering every collection page. */
  collectionPrefix: () => [...profileKeys.all, "collection"] as const,
};

/** t094: server-owned probe jobs. The accepted receipt pre-seeds the detail
 * cache; SSE `probe_job_progress` events keep it current without refetching. */
export const probeJobKeys = {
  all: ["probeJobs"] as const,
  detail: (jobId: string) => [...probeJobKeys.all, "detail", jobId] as const,
};

/** t076 review f003: collection pages live under a separate key
 * prefix from the legacy full list, so every lists() invalidation
 * must also invalidate the collection prefix — otherwise a mutation
 * succeeds and the paged list keeps showing the deleted/created row
 * until the next focus refetch. */
export function invalidateProfileLists(queryClient: QueryClient): void {
  queryClient.invalidateQueries({ queryKey: profileKeys.lists() });
  queryClient.invalidateQueries({
    queryKey: profileKeys.collectionPrefix(),
  });
}

export function invalidateGroupLists(queryClient: QueryClient): void {
  queryClient.invalidateQueries({ queryKey: groupKeys.lists() });
  queryClient.invalidateQueries({
    queryKey: groupKeys.collectionPrefix(),
  });
}

export function invalidateProxyLists(queryClient: QueryClient): void {
  queryClient.invalidateQueries({ queryKey: proxyKeys.lists() });
  queryClient.invalidateQueries({
    queryKey: proxyKeys.collectionPrefix(),
  });
}

export function useProfilesQuery(
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProfileResponse[], Error> {
  return useQuery({
    queryKey: profileKeys.lists(),
    queryFn: () => client.profiles.list(),
  });
}

export interface ProfilesCollectionParams {
  search?: string;
  group_id?: string;
  proxy_id?: string;
  status?: string;
  platform?: string;
  sort?: "default" | "manual" | "name" | "recent" | "created";
  page?: number;
  page_size?: number;
}

/** t076 AC-001: bounded server-side profile page. */
export function useProfilesCollectionQuery(
  params: ProfilesCollectionParams,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProfileCollectionPage, Error> {
  return useQuery({
    queryKey: profileKeys.collection(params),
    queryFn: () => client.profiles.listCollection(params),
  });
}

/** t076 review f008: walk every page of a profile collection query
 * until the server total is collected. One page can never stand in
 * for "all matching rows": the entry page has no pager, and even an
 * exact-status page is capped at 100 rows. The loop stops on the
 * server total, or on an empty page if the total ever disagrees.
 * The key stays under the collection prefix so list invalidations
 * refetch it. */
export function useAllProfilesCollectionQuery(
  params: Omit<ProfilesCollectionParams, "page">,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProfileResponse[], Error> {
  return useQuery({
    queryKey: [...profileKeys.collection(params), "all-pages"] as const,
    queryFn: async () => {
      const items: ProfileResponse[] = [];
      let page = 1;
      for (;;) {
        const chunk = await client.profiles.listCollection({
          ...params,
          page,
          page_size: params.page_size ?? 100,
        });
        // CollectionPage.items is optional in the generated type (the
        // field carries a server default), so an absent page is an
        // empty page, not a crash.
        const pageItems = chunk.items ?? [];
        items.push(...pageItems);
        if (
          pageItems.length === 0 ||
          page * chunk.page_size >= chunk.total
        ) {
          break;
        }
        page += 1;
      }
      return items;
    },
  });
}

/** t076 AC-002: one batched runtime read for all profiles. */
export function useRuntimeSummaryQuery(
  client: ApiClient = defaultApiClient,
  options: { enabled?: boolean } = {},
): UseQueryResult<RuntimeSummaryResponse, Error> {
  return useQuery({
    queryKey: profileKeys.runtimeSummary(),
    queryFn: () => client.profiles.getRuntimeSummary(),
    enabled: options.enabled ?? true,
  });
}

/** t076 AC-006: bounded profile name search. */
export function useProfileCandidatesQuery(
  search: string,
  limit = 20,
  client: ApiClient = defaultApiClient,
): UseQueryResult<CandidateEntry[], Error> {
  return useQuery({
    queryKey: [...profileKeys.all, "candidates", search, limit] as const,
    queryFn: () => client.profiles.listCandidates(search, limit),
  });
}

/** t076 review f006: bounded group name search, for filter options
 * and move menus that must not fetch the whole group table. */
export function useGroupCandidatesQuery(
  search: string,
  limit = 50,
  client: ApiClient = defaultApiClient,
): UseQueryResult<CandidateEntry[], Error> {
  return useQuery({
    queryKey: [...groupKeys.all, "candidates", search, limit] as const,
    queryFn: () => client.groups.listCandidates(search, limit),
  });
}

/** t076 review f006: bounded proxy name search, for filter options
 * that must not fetch the whole proxy table. */
export function useProxyCandidatesQuery(
  search: string,
  limit = 50,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProxyCandidateEntry[], Error> {
  return useQuery({
    queryKey: [...proxyKeys.all, "candidates", search, limit] as const,
    queryFn: () => client.proxies.listCandidates(search, limit),
  });
}

/** t076 review f006: one group by id — echoes a selected filter
 * value that falls outside the bounded candidate page. */
export function useGroupQuery(
  groupId: string | null | undefined,
  client: ApiClient = defaultApiClient,
): UseQueryResult<GroupResponse, Error> {
  return useQuery({
    queryKey: [...groupKeys.all, "detail", groupId || ""] as const,
    queryFn: () => client.groups.get(groupId!),
    enabled: Boolean(groupId),
  });
}

/** t076 review f006: one proxy by id — echoes a selected filter
 * value that falls outside the bounded candidate page. */
export function useProxyQuery(
  proxyId: string | null | undefined,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProxyResponse, Error> {
  return useQuery({
    queryKey: [...proxyKeys.all, "detail", proxyId || ""] as const,
    queryFn: () => client.proxies.get(proxyId!),
    enabled: Boolean(proxyId),
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
  keyOptions?: { keySource?: () => string },
): UseMutationResult<ProfileResponse, Error, ProfileCreateRequest> {
  const queryClient = useQueryClient();
  return useActionKeyMutation(
    {
      mutationFn: ({ input, actionKey }) =>
        client.profiles.create(input, actionKey),
      onSuccess: () => {
        invalidateProfileLists(queryClient);
      },
    },
    keyOptions,
  );
}

export function useUpdateProfileMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileResponse, Error, { id: string; data: ProfileUpdateRequest }> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.profiles.update(input.id, input.data, actionKey),
    onSuccess: async (data, { input }) => {
      // t058 A24: cancel any in-flight detail fetch before writing the
      // saved profile, so a stale GET resolving after the save cannot
      // overwrite it. The detail query is not invalidated — invalidation
      // would refetch and could reintroduce the same race — only the
      // list is invalidated.
      await queryClient.cancelQueries({
        queryKey: profileKeys.detail(input.id),
      });
      queryClient.setQueryData(profileKeys.detail(input.id), data);
      invalidateProfileLists(queryClient);
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
      invalidateProfileLists(queryClient);
    },
  });
}

/** t078: deletion lifecycle hooks. The batch query polls while any
 * target is non-terminal and invalidates the profile lists as targets
 * reach ``done``, so the list converges even if the progress dialog
 * is closed mid-run (the intent itself is durable server-side). */
export const deletionKeys = {
  all: ["profile-deletions"] as const,
  batch: (batchId: string) =>
    [...deletionKeys.all, "batch", batchId] as const,
};

export function useCreateDeletionsMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileDeletionBatchResponse, Error, string[]> {
  return useMutation({
    mutationFn: (profileIds: string[]) =>
      client.profiles.createDeletions(profileIds),
  });
}

export function useDeletionBatchQuery(
  batchId: string | null,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProfileDeletionBatchResponse> {
  const queryClient = useQueryClient();
  const result = useQuery({
    queryKey: deletionKeys.batch(batchId ?? ""),
    queryFn: () => client.profiles.getDeletionBatch(batchId!),
    enabled: batchId !== null,
    refetchInterval: (query) => {
      const operations = query.state.data?.operations ?? [];
      return operations.some(
        (op) => op.stage !== "done" && op.stage !== "failed",
      )
        ? 1000
        : false;
    },
  });
  const doneIds = (result.data?.operations ?? [])
    .filter((op) => op.stage === "done")
    .map((op) => op.profile_id)
    .join(",");
  useEffect(() => {
    if (doneIds) {
      invalidateProfileLists(queryClient);
    }
  }, [doneIds, queryClient]);
  return result;
}

export function useRetryDeletionMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProfileDeletionOperation, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (operationId: string) =>
      client.profiles.retryDeletion(operationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: deletionKeys.all });
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
      invalidateProfileLists(queryClient);
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
      invalidateProfileLists(queryClient);
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
      invalidateProfileLists(queryClient);
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
      invalidateProfileLists(queryClient);
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
      invalidateProfileLists(queryClient);
      queryClient.invalidateQueries({ queryKey: profileKeys.detail(id) });
    },
  });
}

/** Fields shared by one per-profile runtime response and one
 * batched summary entry — an SSE runtime event merges into both from
 * the same fields (t076 review f001/f002). */
interface RuntimeSharedFields {
  desired_state: "stopped" | "running";
  observed_state: "stopped" | "starting" | "running" | "stopping" | "error";
  runtime_instance_id?: string | null;
  config_version: number;
  failure_count: number;
  restart_blocked: boolean;
  last_started_at?: string | null;
  last_stopped_at?: string | null;
  last_coordinator_error?: string | null;
  updated_at: string;
}

export function useProfileEventsSync(sseClient: ProfileEventsClient): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    const unsubscribe = sseClient.onEvent((event) => {
      const old = queryClient.getQueryData<ProfileRuntimeResponse>(
        profileKeys.runtime(event.profile_id),
      );
      const summary = queryClient.getQueryData<RuntimeSummaryResponse>(
        profileKeys.runtimeSummary(),
      );
      const summaryEntry = summary?.entries.find(
        (entry) => entry.profile_id === event.profile_id,
      );
      // t076 review f001: the summary update is decoupled from the
      // per-profile runtime cache. List/entry pages read only the
      // batched summary, so on first open the runtime cache is empty
      // and the old early return discarded every event. The runtime
      // entry itself is still never synthesized from an event.
      // t076 review f009: each cache fences by its OWN version and
      // instance. The two caches usually disagree on version (the
      // summary is refetched on every list focus/remount; the runtime
      // cache only on a detail visit), so one fence taken from
      // whichever cache exists first lets a late event roll the newer
      // cache back to old data. An event below a cache's version, or
      // from a different instance at the same version, skips that
      // cache only and may still update the other one.
      if (!old && !summaryEntry) return;
      const fenceAllows = (cached: {
        config_version: number;
        runtime_instance_id?: string | null;
      }): boolean => {
        // Events without a version predate the fence and are treated
        // as current for this cache.
        const eventVersion = event.config_version ?? cached.config_version;
        if (eventVersion < cached.config_version) return false;
        if (
          eventVersion === cached.config_version &&
          event.runtime_instance_id != null &&
          cached.runtime_instance_id != null &&
          event.runtime_instance_id !== cached.runtime_instance_id
        ) {
          return false;
        }
        return true;
      };
      const runtimeAllowed = old ? fenceAllows(old) : false;
      const summaryAllowed = summaryEntry ? fenceAllows(summaryEntry) : false;
      if (!runtimeAllowed && !summaryAllowed) return;
      // t076 review f002: the event's start/stop timestamps, failure
      // count, restart flag and updated timestamp travel into both
      // caches; a time-only event is a real change, not a duplicate.
      // A field the event omits keeps the cached value.
      const mergeShared = <T extends RuntimeSharedFields>(base: T): T => ({
        ...base,
        desired_state: event.desired_state ?? base.desired_state,
        observed_state: event.observed_state ?? base.observed_state,
        runtime_instance_id:
          event.runtime_instance_id !== undefined
            ? event.runtime_instance_id
            : base.runtime_instance_id,
        config_version: event.config_version ?? base.config_version,
        failure_count: event.failure_count ?? base.failure_count,
        restart_blocked: event.restart_blocked ?? base.restart_blocked,
        last_started_at:
          event.last_started_at !== undefined
            ? event.last_started_at
            : base.last_started_at,
        last_stopped_at:
          event.last_stopped_at !== undefined
            ? event.last_stopped_at
            : base.last_stopped_at,
        last_coordinator_error:
          event.last_coordinator_error !== undefined
            ? event.last_coordinator_error
            : base.last_coordinator_error,
        updated_at: event.updated_at ?? base.updated_at,
      });
      const sharedChanged = (
        next: RuntimeSharedFields,
        base: RuntimeSharedFields,
      ): boolean =>
        next.observed_state !== base.observed_state ||
        next.desired_state !== base.desired_state ||
        next.runtime_instance_id !== base.runtime_instance_id ||
        next.config_version !== base.config_version ||
        next.failure_count !== base.failure_count ||
        next.restart_blocked !== base.restart_blocked ||
        next.last_started_at !== base.last_started_at ||
        next.last_stopped_at !== base.last_stopped_at ||
        next.last_coordinator_error !== base.last_coordinator_error ||
        next.updated_at !== base.updated_at;
      // Per-profile runtime entry: update in place when cached, never
      // synthesize one from an event — and only when this cache's own
      // fence let the event through (t076 review f009).
      let nextRuntime: ProfileRuntimeResponse | undefined;
      let runtimeChanged = false;
      if (old && runtimeAllowed) {
        nextRuntime = {
          ...mergeShared(old),
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
        };
        runtimeChanged =
          sharedChanged(nextRuntime, old) ||
          nextRuntime.control !== old.control ||
          nextRuntime.search_defaults !== old.search_defaults ||
          nextRuntime.transport !== old.transport;
      }
      // Batched summary entry: the same merge, the same duplicate
      // guard — list/entry pages stay correct without a refetch —
      // and only when this entry's own fence let the event through
      // (t076 review f009).
      let nextEntry: RuntimeSummaryEntry | undefined;
      let entryChanged = false;
      if (summaryEntry && summaryAllowed) {
        nextEntry = mergeShared(summaryEntry);
        entryChanged = sharedChanged(nextEntry, summaryEntry);
      }
      // t076 AC-003: a duplicate/replayed event that changes nothing
      // has no side effects — in particular it must not trigger a
      // full list refetch.
      if (!runtimeChanged && !entryChanged) return;
      if (nextRuntime && runtimeChanged) {
        queryClient.setQueryData(
          profileKeys.runtime(event.profile_id),
          nextRuntime,
        );
      }
      if (summary && nextEntry && entryChanged) {
        queryClient.setQueryData<RuntimeSummaryResponse>(
          profileKeys.runtimeSummary(),
          {
            ...summary,
            entries: summary.entries.map((entry) =>
              entry.profile_id === event.profile_id ? nextEntry! : entry,
            ),
            running_count: summary.entries.reduce(
              (count, entry) =>
                count +
                (entry.profile_id === event.profile_id
                  ? nextEntry!.observed_state === "running"
                    ? 1
                    : 0
                  : entry.observed_state === "running"
                    ? 1
                    : 0),
              0,
            ),
          },
        );
      }
    });

    const unsubscribePreview: (() => void) | undefined =
      sseClient.onPreviewEvent?.((event) => {
        const detail = queryClient.getQueryData<ProfileResponse>(
          profileKeys.detail(event.profile_id),
        );
        const listed = queryClient
          .getQueryData<ProfileResponse[]>(profileKeys.lists())
          ?.find((item) => item.id === event.profile_id);
        // List pages read the collection pages now, so the legacy full
        // list is usually empty there — consult the cached collection
        // pages for the preview policy as well.
        const inCollection = queryClient
          .getQueriesData<ProfileCollectionPage>({
            queryKey: profileKeys.collectionPrefix(),
          })
          .flatMap(([, page]) => page?.items ?? [])
          .find((item) => item.id === event.profile_id);
        if (
          detail?.capture_preview === false ||
          listed?.capture_preview === false ||
          inCollection?.capture_preview === false
        )
          return;
        const profile = detail ?? listed ?? inCollection;
        if (profile?.capture_preview !== true) return;
        const captured = Date.parse(event.captured_at);
        if (!Number.isFinite(captured)) return;
        // t076 review f002: a preview capture also moves the summary
        // entry the list rows render, under the same "captured time
        // never goes backwards" fence as the runtime entry.
        queryClient.setQueryData(
          profileKeys.runtime(event.profile_id),
          (old: ProfileRuntimeResponse | undefined) => {
            if (!old) return undefined;
            const previous = old.preview_captured_at
              ? Date.parse(old.preview_captured_at)
              : NaN;
            if (Number.isFinite(previous) && captured <= previous) return old;
            return { ...old, preview_captured_at: event.captured_at };
          },
        );
        queryClient.setQueryData<RuntimeSummaryResponse>(
          profileKeys.runtimeSummary(),
          (summary) => {
            if (!summary) return summary;
            const entry = summary.entries.find(
              (item) => item.profile_id === event.profile_id,
            );
            if (!entry) return summary;
            const previous = entry.preview_captured_at
              ? Date.parse(entry.preview_captured_at)
              : NaN;
            if (Number.isFinite(previous) && captured <= previous)
              return summary;
            return {
              ...summary,
              entries: summary.entries.map((item) =>
                item.profile_id === event.profile_id
                  ? { ...item, preview_captured_at: event.captured_at }
                  : item,
              ),
            };
          },
        );
      });

    // t056 A31: another client's group/proxy write arrives as a
    // reference event — invalidate the reference lists and the Profile
    // list (a profile's group/proxy may have changed) and refetch.
    const unsubscribeReference: (() => void) | undefined =
      sseClient.onReferenceEvent?.((event) => {
        if (event.event === "groups_changed") {
          invalidateGroupLists(queryClient);
        } else {
          invalidateProxyLists(queryClient);
        }
        invalidateProfileLists(queryClient);
      });

    // t094: probe-job progress is authoritative read-model data. Write it
    // straight into the job cache; steady-state progress never triggers a
    // refetch. The proxy lists are refreshed once on submission.
    const unsubscribeProbeJob: (() => void) | undefined =
      sseClient.onProbeJobProgress?.((event) => {
        const { event: _event, ...job } = event;
        // Write the shared job cache key; both the proxy speed-test page and
        // the environment batch bar read this key, so one SSE handler keeps
        // both pages live (t094 AC-005/AC-007).
        queryClient.setQueryData<ProxyProbeJob>(
          probeJobKeys.detail(job.job_id),
          job,
        );
      });

    sseClient.start();

    return () => {
      unsubscribe();
      unsubscribePreview?.();
      unsubscribeReference?.();
      unsubscribeProbeJob?.();
      sseClient.stop();
    };
  }, [sseClient, queryClient]);
}


export const groupKeys = {
  all: ["groups"] as const,
  lists: () => [...groupKeys.all, "list"] as const,
  collection: (params: object) =>
    [...groupKeys.all, "collection", params] as const,
  /** t076 review f003: prefix covering every collection page. */
  collectionPrefix: () => [...groupKeys.all, "collection"] as const,
};

export const proxyKeys = {
  all: ["proxies"] as const,
  lists: () => [...proxyKeys.all, "list"] as const,
  usedBy: (id: string) => [...proxyKeys.all, "used-by", id] as const,
  collection: (params: object) =>
    [...proxyKeys.all, "collection", params] as const,
  countries: () => [...proxyKeys.all, "countries"] as const,
  /** t076 review f003: prefix covering every collection page. */
  collectionPrefix: () => [...proxyKeys.all, "collection"] as const,
};

export const fontSetKeys = {
  all: ["fontSets"] as const,
  lists: () => [...fontSetKeys.all, "list"] as const,
};

export function useGroupsQuery(
  client: ApiClient = defaultApiClient,
): UseQueryResult<GroupResponse[], Error> {
  return useQuery({
    queryKey: groupKeys.lists(),
    queryFn: () => client.groups.list(),
  });
}

export function useProxiesQuery(
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProxyResponse[], Error> {
  return useQuery({
    queryKey: proxyKeys.lists(),
    queryFn: () => client.proxies.list(),
  });
}

export interface ProxiesCollectionParams {
  search?: string;
  country_code?: string;
  city?: string;
  scheme?: string;
  sort?: "default" | "name";
  page?: number;
  page_size?: number;
}

/** t076 AC-001/AC-006: bounded server-side proxy page. */
export function useProxiesCollectionQuery(
  params: ProxiesCollectionParams,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProxyCollectionPage, Error> {
  return useQuery({
    queryKey: proxyKeys.collection(params),
    queryFn: () => client.proxies.listCollection(params),
  });
}

/** t076 AC-006: stable country -> city ranges for the linked filters. */
export function useProxyCountriesQuery(
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProxyCountryRange[], Error> {
  return useQuery({
    queryKey: proxyKeys.countries(),
    queryFn: () => client.proxies.listCountries(),
  });
}

/** t076 AC-004: used-by detail (same union as the count), fetched only
 * when the user opens it. */
export function useProxyUsedByQuery(
  proxyId: string | null | undefined,
  client: ApiClient = defaultApiClient,
  options: { enabled?: boolean } = {},
): UseQueryResult<ProxyUsedByResponse, Error> {
  return useQuery({
    queryKey: proxyKeys.usedBy(proxyId || ""),
    queryFn: () => client.proxies.getUsedBy(proxyId!),
    enabled: Boolean(proxyId) && (options.enabled ?? true),
  });
}

export function useFontSetsQuery(
  client: ApiClient = defaultApiClient,
): UseQueryResult<FontSetListResponse, Error> {
  return useQuery({
    queryKey: fontSetKeys.lists(),
    queryFn: () => client.fontSets.list(),
  });
}

export function useCreateGroupMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<GroupResponse, Error, GroupCreateRequest> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) => client.groups.create(input, actionKey),
    onSuccess: () => {
      invalidateGroupLists(queryClient);
      invalidateProfileLists(queryClient);
    },
  });
}

export function useUpdateGroupMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<
  GroupResponse,
  Error,
  { groupId: string; data: GroupUpdateRequest }
> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.groups.update(input.groupId, input.data, actionKey),
    onSuccess: () => {
      invalidateGroupLists(queryClient);
      invalidateProfileLists(queryClient);
    },
  });
}

export function useDeleteGroupMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) => client.groups.remove(input, actionKey),
    onSuccess: () => {
      invalidateGroupLists(queryClient);
      invalidateProfileLists(queryClient);
    },
  });
}

export function useReorderGroupsMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<GroupResponse[], Error, { orderedIds: string[] }> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.groups.reorder({ ordered_ids: input.orderedIds }, actionKey),
    onSuccess: () => {
      invalidateGroupLists(queryClient);
    },
  });
}

export function useCreateProxyMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProxyResponse, Error, ProxyCreateRequest> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) => client.proxies.create(input, actionKey),
    onSuccess: () => {
      invalidateProxyLists(queryClient);
      invalidateProfileLists(queryClient);
    },
  });
}

export function useUpdateProxyMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<
  ProxyResponse,
  Error,
  { proxyId: string; data: ProxyUpdateRequest }
> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.proxies.update(input.proxyId, input.data, actionKey),
    onSuccess: () => {
      invalidateProxyLists(queryClient);
      invalidateProfileLists(queryClient);
    },
  });
}

export function useDeleteProxyMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) => client.proxies.remove(input, actionKey),
    onSuccess: () => {
      invalidateProxyLists(queryClient);
      invalidateProfileLists(queryClient);
    },
  });
}

/** t094: submit one server-owned probe job. The 202 receipt is written into
 * the job read-model cache immediately so the page can drive row state before
 * the first SSE snapshot arrives; the proxy lists are invalidated once so
 * fresh observations surface. */
export function useSubmitProbeJobMutation(
  client: ApiClient = defaultApiClient,
): UseMutationResult<ProxyProbeJobAccepted, Error, ProxyProbeJobRequest> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input) => client.probes.createProbeJob(input),
    onSuccess: (accepted, input) => {
      const now = new Date().toISOString();
      const members: ProxyProbeJobMember[] = (input.proxy_ids ?? []).map(
        (proxyId) => ({ proxy_id: proxyId, state: "pending" }),
      );
      queryClient.setQueryData<ProxyProbeJob>(
        probeJobKeys.detail(accepted.job_id),
        {
          job_id: accepted.job_id,
          state: accepted.state,
          total: accepted.total,
          completed: accepted.completed,
          failed: accepted.failed,
          created_at: now,
          updated_at: now,
          members,
        },
      );
      invalidateProxyLists(queryClient);
      invalidateProfileLists(queryClient);
    },
  });
}

/** t094: read one probe job. Pre-seeded from the submit receipt, then kept
 * current by `probe_job_progress` SSE events written directly to this cache. */
export function useProbeJobQuery(
  jobId: string | null | undefined,
  enabled: boolean = true,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProxyProbeJob, Error> {
  return useQuery({
    queryKey: probeJobKeys.detail(jobId || ""),
    queryFn: () => client.probes.getProbeJob(jobId!),
    enabled: Boolean(jobId) && enabled,
    staleTime: 30_000,
  });
}

/** t094 AC-007: read model for a server-driven environment batch job.
 * Uses the same cache key as proxy probe jobs so the single SSE
 * `probe_job_progress` handler keeps both pages live (no key divergence). */
export function useProfileBatchJobQuery(
  jobId: string | null | undefined,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ProxyProbeJob, Error> {
  return useQuery({
    queryKey: probeJobKeys.detail(jobId || ""),
    queryFn: () => client.profileBatchJobs.get(jobId!),
    enabled: Boolean(jobId),
    staleTime: 30_000,
  });
}
