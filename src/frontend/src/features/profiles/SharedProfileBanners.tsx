import { Banner, Button } from "../../shared/ui";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import {
  useApplyDisplaySettingsMutation,
  useProfileQuery,
  useProfileRuntimeQuery,
  useRetrySearchDefaultsMutation,
} from "./useProfilesQuery";

export function SharedProfileBanners({ profileId }: { profileId: string }) {
  const { t } = useI18n();
  const client = useApiClient();
  const { data: profile } = useProfileQuery(profileId, client);
  const { data: runtime } = useProfileRuntimeQuery(profileId, client);
  const retryMutation = useRetrySearchDefaultsMutation(client);
  const applyMutation = useApplyDisplaySettingsMutation(client);

  const searchDefaultsFailed =
    runtime?.search_defaults?.state === "failed";
  const displayPending = Boolean(
    runtime &&
      profile &&
      runtime.config_version !== profile.current_config_version &&
      profile.current_config_version !== undefined,
  );

  return (
    <div data-testid="profile-shared-banners" className="flex flex-col gap-sm">
      {searchDefaultsFailed && (
        <Banner tone="warning" testId="profile-search-defaults-failed">
          <span>{t("detailSearchDefaultsFailed")}</span>
          <Button
            size="sm"
            disabled={retryMutation.isPending}
            onClick={() => retryMutation.mutate(profileId)}
          >
            {t("detailRetrySearchDefaults")}
          </Button>
        </Banner>
      )}
      {displayPending && (
        <Banner tone="warning" testId="profile-apply-pending">
          <span>{t("detailApplyPending")}</span>
          <Button
            size="sm"
            disabled={applyMutation.isPending}
            onClick={() => applyMutation.mutate(profileId)}
          >
            {t("detailApplyAndRestart")}
          </Button>
        </Banner>
      )}
      {applyMutation.isError && (
        <Banner tone="danger" testId="profile-apply-error">
          {t("detailApplyError")}
        </Banner>
      )}
    </div>
  );
}
