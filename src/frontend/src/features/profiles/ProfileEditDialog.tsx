import { useState } from "react";
import { Banner, Dialog } from "../../shared/ui";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import type {
  ProfileCreateRequest,
  ProfileResponse,
  ProfileUpdateRequest,
} from "../../shared/api/types";
import { useUpdateProfileMutation } from "./useProfilesQuery";
import { ProfileForm } from "./ProfileForm";

export function ProfileEditDialog({
  open,
  profile,
  onOpenChange,
}: {
  open: boolean;
  profile: ProfileResponse | null;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useI18n();
  const client = useApiClient();
  const updateMutation = useUpdateProfileMutation(client);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleOpenChange = (nextOpen: boolean) => {
    setSaveError(null);
    onOpenChange(nextOpen);
  };

  const handleSubmit = async (
    values: ProfileCreateRequest | ProfileUpdateRequest,
  ) => {
    if (!profile) return;
    setSaveError(null);
    try {
      await updateMutation.mutateAsync({
        id: profile.id,
        data: values as ProfileUpdateRequest,
      });
    } catch (err) {
      const reason = err instanceof Error ? err.message : String(err);
      setSaveError(t("formSaveFailed", { error: reason }));
      return;
    }
    onOpenChange(false);
  };

  return (
    <Dialog
      trigger={<span />}
      title={t("envEdit")}
      size="lg"
      open={open}
      onOpenChange={handleOpenChange}
    >
      <div data-testid="env-edit-dialog" className="flex flex-col gap-md">
        {saveError ? (
          <Banner tone="danger" testId="env-edit-error">
            {saveError}
          </Banner>
        ) : null}
        {profile ? (
          <ProfileForm
            key={profile.id}
            mode="edit"
            initial={profile}
            onSubmit={handleSubmit}
            submitLabel={t("formSave")}
            isPending={updateMutation.isPending}
          />
        ) : null}
      </div>
    </Dialog>
  );
}
