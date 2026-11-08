import { useI18n } from "../i18n";
import { Button } from "../shared/ui";

export const defaultRecoveryActions = {
  reload: () => window.location.reload(),
  back: () => window.location.replace("/"),
};

export interface AppErrorPageProps {
  onReload?: () => void;
  onBack?: () => void;
}

export function AppErrorPage({ onReload, onBack }: AppErrorPageProps) {
  const { t } = useI18n();
  const reload = onReload ?? defaultRecoveryActions.reload;
  const back = onBack ?? defaultRecoveryActions.back;
  return (
    <div
      data-testid="app-error-page"
      role="alert"
      className="flex min-h-screen items-center justify-center bg-surface p-md"
    >
      <div className="flex w-full max-w-panel flex-col gap-md rounded-lg border border-outline bg-surface-subtle p-lg">
        <h1 className="font-ui text-headline-md text-on-surface">
          {t("errorBoundaryTitle")}
        </h1>
        <p className="font-ui text-body-sm text-on-surface-muted">
          {t("errorBoundaryDescription")}
        </p>
        <div className="flex flex-wrap gap-sm">
          <Button
            variant="primary"
            data-testid="app-error-reload"
            onClick={() => reload()}
          >
            {t("errorBoundaryReload")}
          </Button>
          <Button
            variant="secondary"
            data-testid="app-error-back"
            onClick={() => back()}
          >
            {t("errorBoundaryBack")}
          </Button>
        </div>
      </div>
    </div>
  );
}
