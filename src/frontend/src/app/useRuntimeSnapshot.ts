import { useRuntimeSummaryQuery } from "../features/profiles/useProfilesQuery";
import type { ApiClient } from "../shared/api/client";

export interface RuntimeSnapshot {
  runningCount: number;
  coordinatorError: string | null;
}

/** t076 AC-002: the global snapshot reads one batched summary payload
 * instead of issuing one runtime HTTP request per profile. */
export function useRuntimeSnapshot(client: ApiClient): RuntimeSnapshot {
  const { data: summary } = useRuntimeSummaryQuery(client);
  const entries = summary?.entries ?? [];
  let coordinatorError: string | null = null;
  for (const entry of entries) {
    if (!coordinatorError && entry.last_coordinator_error) {
      coordinatorError = entry.last_coordinator_error;
    }
  }
  return {
    runningCount: summary?.running_count ?? 0,
    coordinatorError,
  };
}
