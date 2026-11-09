import { useState } from "react";
import { useNavigate } from "react-router";
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
  const navigate = useNavigate();
  const { data: runtime } = useProfileRuntimeQuery(profileId, client);
  const duplicateMutation = useDuplicateProfileMutation(client);
  const resetMutation = useResetProfileMutation(client);
  const deleteMutation = useDeleteProfileMutation(client);
  const [error, setError] = useState<string | null>(null);
  const [confirmingReset, setConfirmingReset] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const running = runtime ? runtime.observed_state !== "stopped" : true;

  const reportError = (err: unknown, fallback: string) => {
    setError(err instanceof Error ? err.message : fallback);
  };

  const handleDuplicate = (includeBrowserState: boolean) => {
    setError(null);
    duplicateMutation.mutate(
      { id: profileId, includeBrowserState },
      { onError: (err) => reportError(err, t("failedToDuplicateProfile")) },
    );
  };

  const handleResetConfirm = async () => {
    setError(null);
    try {
      await resetMutation.mutateAsync(profileId);
      setConfirmingReset(false);
    } catch (err: unknown) {
      reportError(err, t("failedToResetProfile"));
    }
  };

  const handleDelete = async () => {
    setError(null);
    try {
      await deleteMutation.mutateAsync(profileId);
      setConfirmingDelete(false);
      navigate("/", { replace: true });
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
            disabled={duplicateMutation.isPending}
            onClick={() => handleDuplicate(false)}
          >
            {t("maintenanceDuplicateConfigOnly")}
          </Button>
          <Button
            variant="secondary"
            disabled={running || duplicateMutation.isPending}
            onClick={() => handleDuplicate(true)}
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
        <div className="flex flex-wrap items-center gap-sm">
          <Button
            variant="danger"
            disabled={resetMutation.isPending}
            data-testid="profile-maintenance-reset-request"
            onClick={() => setConfirmingReset(true)}
          >
            {t("maintenanceResetRequest")}
          </Button>
          {confirmingReset && (
            <>
              <Button
                variant="danger"
                disabled={resetMutation.isPending}
                data-testid="profile-maintenance-reset-confirm"
                onClick={() => void handleResetConfirm()}
              >
                {t("maintenanceResetConfirm")}
              </Button>
              <Button
                variant="secondary"
                data-testid="profile-maintenance-reset-cancel"
                onClick={() => setConfirmingReset(false)}
              >
                {t("cancel")}
              </Button>
            </>
          )}
        </div>
      </section>

      <section
        data-testid="profile-maintenance-delete"
        className="flex flex-col gap-sm rounded-md border border-outline bg-surface p-md"
      >
        <h2 className="font-ui text-headline-md text-on-surface">
          {t("maintenanceDeleteTitle")}
        </h2>
        <div className="flex flex-wrap items-center gap-sm">
          <Button
            variant="danger"
            disabled={running || deleteMutation.isPending}
            data-testid="profile-maintenance-delete-request"
            onClick={() => setConfirmingDelete(true)}
          >
            {t("delete")}
          </Button>
          {confirmingDelete && (
            <>
              <span className="font-ui text-body-sm text-on-surface">
                {t("maintenanceDeleteConfirm")}
              </span>
              <Button
                variant="danger"
                disabled={running || deleteMutation.isPending}
                data-testid="profile-maintenance-delete-confirm"
                onClick={() => void handleDelete()}
              >
                {t("delete")}
              </Button>
              <Button
                variant="secondary"
                data-testid="profile-maintenance-delete-cancel"
                onClick={() => setConfirmingDelete(false)}
              >
                {t("cancel")}
              </Button>
            </>
          )}
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
