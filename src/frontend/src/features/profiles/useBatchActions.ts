import { useCallback, useState } from "react";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import { useToast } from "../../shared/ui";
import type { EnvironmentRow } from "./EnvironmentTable";
import type { ProfileBatchJobRequest } from "../../shared/api/types";

/** t078: batch deletion no longer loops single DELETEs here; it goes
 * through the deletion dialog and the durable batch endpoint. */
export type BatchAction = ProfileBatchJobRequest["action"];

export interface BatchRunOptions {
  groupId?: string | null;
}

export function useBatchActions({
  selected,
  rows,
  clearSelection,
}: {
  selected: Set<string>;
  rows: EnvironmentRow[];
  clearSelection: (succeededIds: string[]) => void;
}): {
  run: (action: BatchAction, options?: BatchRunOptions) => Promise<string | null>;
  pending: boolean;
} {
  const { t } = useI18n();
  const client = useApiClient();
  const { show } = useToast();
  const [pending, setPending] = useState(false);

  const run = useCallback(
    async (action: BatchAction, options: BatchRunOptions = {}) => {
      const profileIds = rows
        .filter((row) => selected.has(row.profile.id))
        .map((row) => row.profile.id);
      if (profileIds.length === 0) return null;
      setPending(true);
      try {
        // t094 AC-007: submit one durable server-side job. The target set
        // and action are frozen at submission; progress is delivered over
        // SSE like proxy probe jobs, never driven by a client-side loop.
        const receipt = await client.profileBatchJobs.submit({
          action,
          profile_ids: profileIds,
          group_id: options.groupId ?? null,
        });
        show(t("envBatchSubmitted", { count: receipt.total }));
        // The job owns the per-target outcome; clear the selection now so
        // the UI does not keep stale rows selected while the job runs.
        clearSelection(profileIds);
        return receipt.job_id;
      } finally {
        setPending(false);
      }
    },
    [rows, selected, clearSelection, client, show, t],
  );

  return { run, pending };
}
