import { useI18n } from "../../i18n";
import { Button } from "../../shared/ui";

export function BatchActionBar({
  count,
  onStart,
  onStop,
  onMove,
  onDelete,
  pending,
}: {
  count: number;
  onStart: () => void;
  onStop: () => void;
  onMove: () => void;
  onDelete: () => void;
  pending: boolean;
}) {
  const { t } = useI18n();
  return (
    <div
      data-testid="env-batch-bar"
      className="fixed bottom-lg left-1/2 z-30 flex -translate-x-1/2 flex-wrap items-center gap-sm rounded-xl border border-outline bg-surface-raised px-md py-sm shadow-lg"
    >
      <span className="font-ui text-label-md text-on-surface">
        {t("envSelected", { count })}
      </span>
      <Button
        data-testid="env-batch-start"
        size="sm"
        disabled={pending}
        onClick={onStart}
      >
        {t("envBatchStart")}
      </Button>
      <Button
        data-testid="env-batch-stop"
        size="sm"
        disabled={pending}
        onClick={onStop}
      >
        {t("envBatchStop")}
      </Button>
      <Button
        data-testid="env-batch-move"
        size="sm"
        disabled={pending}
        onClick={onMove}
      >
        {t("envBatchMove")}
      </Button>
      <Button
        data-testid="env-batch-delete"
        size="sm"
        variant="danger"
        disabled={pending}
        onClick={onDelete}
      >
        {t("envBatchDelete")}
      </Button>
    </div>
  );
}
