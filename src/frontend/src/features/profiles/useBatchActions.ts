import { useCallback, useState } from "react";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import { useToast } from "../../shared/ui";
import type { EnvironmentRow } from "./EnvironmentTable";
import {
  useDeleteProfileMutation,
  useSetDesiredStateMutation,
  useStopProfileMutation,
  useUpdateProfileMutation,
} from "./useProfilesQuery";

export type BatchAction = "start" | "stop" | "moveToGroup" | "delete";

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
  run: (action: BatchAction, options?: BatchRunOptions) => Promise<void>;
  pending: boolean;
} {
  const { t } = useI18n();
  const client = useApiClient();
  const { show } = useToast();
  const [pending, setPending] = useState(false);
  const startMutation = useSetDesiredStateMutation(client);
  const stopMutation = useStopProfileMutation(client);
  const updateMutation = useUpdateProfileMutation(client);
  const deleteMutation = useDeleteProfileMutation(client);

  const run = useCallback(
    async (action: BatchAction, options: BatchRunOptions = {}) => {
      const targets = rows.filter((row) => selected.has(row.profile.id));
      const succeeded: string[] = [];
      let failed = 0;
      setPending(true);
      try {
        for (const row of targets) {
          const id = row.profile.id;
          try {
            switch (action) {
              case "start":
                await startMutation.mutateAsync({ id, state: "running" });
                break;
              case "stop":
                await stopMutation.mutateAsync(id);
                break;
              case "moveToGroup":
                await updateMutation.mutateAsync({
                  id,
                  data: { group_id: options.groupId ?? null },
                });
                break;
              case "delete":
                await deleteMutation.mutateAsync(id);
                break;
            }
            succeeded.push(id);
          } catch {
            failed += 1;
          }
        }
      } finally {
        show(t("envBatchResult", { success: succeeded.length, failed }));
        clearSelection(succeeded);
        setPending(false);
      }
    },
    [
      rows,
      selected,
      clearSelection,
      startMutation,
      stopMutation,
      updateMutation,
      deleteMutation,
      show,
      t,
    ],
  );

  return { run, pending };
}
