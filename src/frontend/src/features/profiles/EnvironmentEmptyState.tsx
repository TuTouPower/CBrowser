import { useI18n } from "../../i18n";
import { Button, EmptyState } from "../../shared/ui";

export function EnvironmentEmptyState({
  filtered,
  onNew,
  onClearFilters,
}: {
  filtered: boolean;
  onNew: () => void;
  onClearFilters: () => void;
}) {
  const { t } = useI18n();
  return (
    <div data-testid="env-empty-state">
      {filtered ? (
        <EmptyState
          title={t("envNoResults")}
          action={
            <Button
              data-testid="env-clear-filters-empty"
              onClick={onClearFilters}
            >
              {t("envClearFilters")}
            </Button>
          }
        />
      ) : (
        <EmptyState
          title={t("envEmptyTitle")}
          action={
            <Button
              data-testid="env-empty-create"
              variant="primary"
              onClick={onNew}
            >
              {t("envEmptyAction")}
            </Button>
          }
        />
      )}
    </div>
  );
}
