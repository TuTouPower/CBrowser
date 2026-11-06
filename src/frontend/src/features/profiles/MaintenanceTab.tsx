import { useState } from "react";
import { Banner, Button } from "../../shared/ui";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import { ApiError } from "../../shared/api/client";
import {
  useDeleteProfileMutation,
  useDuplicateProfileMutation,
  useProfileRuntimeQuery,
  useResetProfileMutation,
} from "./useProfilesQuery";

export function MaintenanceTab({ profileId }: { profileId: string }) {
  const { t } = useI18n();
  const client = useApiClient();
  const { data: runtime } = useProfileRuntimeQuery(profileId, client);
  const duplicateMutation = useDuplicateProfileMutation(client);
  const resetMutation = useResetProfileMutation(client);
  const deleteMutation = useDeleteProfileMutation(client);
  const [error, setError] = useState<string | null>(null);

  const running = runtime ? runtime.observed_state !== "stopped" : true;

  const handleDelete = async () => {
    setError(null);
    try {
      await deleteMutation.mutateAsync(profileId);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.errorCode === "profile_running") {
        setError(t("maintenanceDeleteRunningDisabled"));
      } else {
        setError(
          err instanceof Error ? err.message : t("failedToDeleteProfile"),
        );
      }
    }
  };

  return (
    <div
      data-testid="profile-maintenance-tab"
      className="flex flex-col gap-md"
    >
      {error && (
        <Banner tone="danger" testId="profile-maintenance-error">
          {error}
        </Banner>
      )}

      <section
        data-testid="profile-maintenance-duplicate"
        className="flex flex-col gap-sm rounded-md border border-outline bg-surface p-md"
      >
        <h2 className="font-ui text-headline-md text-on-surface">
          {t("maintenanceDuplicateTitle")}
        </h2>
        <div className="flex flex-wrap gap-sm">
          <Button
            variant="secondary"
            onClick={() =>
              duplicateMutation.mutate({
                id: profileId,
                includeBrowserState: false,
              })
            }
          >
            {t("maintenanceDuplicateConfigOnly")}
          </Button>
          <Button
            variant="secondary"
            disabled={running}
            onClick={() =>
              duplicateMutation.mutate({
                id: profileId,
                includeBrowserState: true,
              })
            }
          >
            {t("maintenanceDuplicateWithState")}
          </Button>
        </div>
        {running && (
          <p className="font-ui text-label-sm text-on-surface-muted">
            {t("maintenanceDuplicateRunningDisabled")}
          </p>
        )}
      </section>

      <section
        data-testid="profile-maintenance-reset"
        className="flex flex-col gap-sm rounded-md border border-outline bg-surface p-md"
      >
        <h2 className="font-ui text-headline-md text-on-surface">
          {t("maintenanceResetTitle")}
        </h2>
        <ul className="flex flex-col gap-xs font-ui text-body-sm text-on-surface-muted">
          <li>{t("maintenanceResetClear")}</li>
          <li>{t("maintenanceResetKeep")}</li>
        </ul>
        <div>
          <Button variant="danger" onClick={() => resetMutation.mutate(profileId)}>
            {t("maintenanceResetConfirm")}
          </Button>
        </div>
      </section>

      <section
        data-testid="profile-maintenance-delete"
        className="flex flex-col gap-sm rounded-md border border-outline bg-surface p-md"
      >
        <h2 className="font-ui text-headline-md text-on-surface">
          {t("maintenanceDeleteTitle")}
        </h2>
        <div>
          <Button
            variant="danger"
            disabled={running || deleteMutation.isPending}
            onClick={() => void handleDelete()}
          >
            {t("delete")}
          </Button>
        </div>
        {running && (
          <p className="font-ui text-label-sm text-on-surface-muted">
            {t("maintenanceDeleteRunningDisabled")}
          </p>
        )}
      </section>
    </div>
  );
}
