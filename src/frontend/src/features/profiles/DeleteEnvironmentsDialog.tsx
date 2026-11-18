import { useI18n, type TranslationKey } from "../../i18n";
import type { ProfileDeletionOperation } from "../../shared/api/types";
import { Button, Dialog } from "../../shared/ui";
import type { EnvironmentRow } from "./EnvironmentTable";

/** t078: one centered modal for single and batch deletion.
 *
 * The target set is frozen by the caller when the dialog opens
 * (AC-005: page/filter changes afterwards cannot widen it). Nothing
 * is sent before the explicit confirm (AC-002); after confirming, the
 * dialog shows the durable per-target stages from the server, with
 * failed targets keeping their stage, error and a retry entry
 * (AC-003/AC-005). Closing the dialog never cancels the server-side
 * deletion (AC-004). */
export interface DeleteDialogTarget {
  id: string;
  name: string;
  running: boolean;
}

export function deleteTargetsFromRows(
  rows: EnvironmentRow[],
): DeleteDialogTarget[] {
  return rows.map((row) => {
    const observed = row.runtime?.observed_state ?? "stopped";
    return {
      id: row.profile.id,
      name: row.profile.name,
      running: observed === "running" || observed === "starting",
    };
  });
}

const STAGE_LABEL: Record<string, TranslationKey> = {
  accepted: "envDeleteStageAccepted",
  stopping: "envDeleteStageStopping",
  cleaning: "envDeleteStageCleaning",
  done: "envDeleteStageDone",
  failed: "envDeleteStageFailed",
};

export function DeleteEnvironmentsDialog({
  open,
  targets,
  operations,
  creating,
  createError,
  onConfirm,
  onRetry,
  onOpenChange,
}: {
  open: boolean;
  targets: DeleteDialogTarget[];
  operations: ProfileDeletionOperation[] | null;
  creating: boolean;
  createError: string | null;
  onConfirm: () => void;
  onRetry: (operationId: string) => void;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useI18n();
  const started = operations !== null;
  const settled =
    started &&
    operations.every(
      (op) => op.stage === "done" || op.stage === "failed",
    );
  const anyRunning = targets.some((target) => target.running);
  const title = !started
    ? t("envDeleteConfirmTitle")
    : settled
      ? t("envDeleteResultTitle")
      : t("envDeleteProgressTitle");
  const operationByProfile = new Map(
    (operations ?? []).map((op) => [op.profile_id, op]),
  );

  return (
    <Dialog
      trigger={<span />}
      title={title}
      open={open}
      onOpenChange={onOpenChange}
    >
      <div
        data-testid="env-delete-dialog"
        className="flex flex-col gap-md"
      >
        {!started ? (
          <>
            <p className="font-ui text-body-md text-on-surface">
              {targets.length === 1
                ? t("envDeleteConfirm", { name: targets[0]!.name })
                : t("envBatchDeleteConfirm", { count: targets.length })}
            </p>
            {anyRunning && (
              <p
                data-testid="env-delete-running-note"
                className="font-ui text-body-sm text-on-surface-muted"
              >
                {t("envDeleteRunningNote")}
              </p>
            )}
            <ul className="flex flex-col gap-xs">
              {targets.map((target) => (
                <li
                  key={target.id}
                  data-testid={`env-delete-target-${target.id}`}
                  className="font-ui text-body-sm text-on-surface"
                >
                  {target.name}
                </li>
              ))}
            </ul>
            {createError && (
              <p
                data-testid="env-delete-create-error"
                className="font-ui text-body-sm text-danger"
              >
                {createError}
              </p>
            )}
            <div className="flex justify-end gap-sm">
              <Button
                data-testid="env-delete-cancel"
                onClick={() => onOpenChange(false)}
              >
                {t("cancel")}
              </Button>
              <Button
                data-testid="env-delete-accept"
                variant="danger"
                disabled={creating}
                onClick={onConfirm}
              >
                {t("envDelete")}
              </Button>
            </div>
          </>
        ) : (
          <>
            <ul className="flex flex-col gap-sm">
              {targets.map((target) => {
                const op = operationByProfile.get(target.id);
                const stage = op?.stage ?? "accepted";
                return (
                  <li
                    key={target.id}
                    data-testid={`env-delete-op-${target.id}`}
                    className="flex flex-wrap items-center gap-sm"
                  >
                    <span className="font-ui text-body-sm text-on-surface">
                      {op?.profile_name ?? target.name}
                    </span>
                    <span
                      data-testid={`env-delete-stage-${target.id}`}
                      className="font-ui text-label-sm text-on-surface-muted"
                    >
                      {t(STAGE_LABEL[stage] ?? "envDeleteStageAccepted")}
                      {stage === "failed" && op?.failed_stage
                        ? ` (${t(
                            STAGE_LABEL[op.failed_stage] ??
                              "envDeleteStageFailed",
                          )})`
                        : ""}
                    </span>
                    {stage === "failed" && op && (
                      <>
                        <span
                          data-testid={`env-delete-error-${target.id}`}
                          className="font-ui text-body-sm text-danger"
                        >
                          {op.error ?? ""}
                        </span>
                        <Button
                          size="sm"
                          data-testid={`env-delete-retry-${target.id}`}
                          onClick={() => onRetry(op.id)}
                        >
                          {t("retryAction")}
                        </Button>
                      </>
                    )}
                  </li>
                );
              })}
            </ul>
            <div className="flex justify-end gap-sm">
              <Button
                data-testid="env-delete-close"
                onClick={() => onOpenChange(false)}
              >
                {settled ? t("envDeleteDoneButton") : t("cancel")}
              </Button>
            </div>
          </>
        )}
      </div>
    </Dialog>
  );
}
