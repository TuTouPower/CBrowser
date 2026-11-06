import { useQueries } from "@tanstack/react-query";
import {
  profileKeys,
  useProfilesQuery,
} from "../features/profiles/useProfilesQuery";
import type { ApiClient } from "../shared/api/client";
import type { ProfileRuntimeResponse } from "../shared/api/types";

export interface RuntimeSnapshot {
  runningCount: number;
  coordinatorError: string | null;
}

export function useRuntimeSnapshot(client: ApiClient): RuntimeSnapshot {
  const { data: profiles = [] } = useProfilesQuery(client);
  const queries = useQueries({
    queries: profiles.map((profile) => ({
      queryKey: profileKeys.runtime(profile.id),
      queryFn: () => client.profiles.getRuntime(profile.id),
    })),
  });

  let runningCount = 0;
  let coordinatorError: string | null = null;
  for (const query of queries) {
    const data = query.data as ProfileRuntimeResponse | undefined;
    if (!data) continue;
    if (data.observed_state === "running") runningCount += 1;
    if (!coordinatorError && data.last_coordinator_error) {
      coordinatorError = data.last_coordinator_error;
    }
  }
  return { runningCount, coordinatorError };
}
