import { useCallback, useState } from "react";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import type {
  ProfileCreateRequest,
  ProfileUpdateRequest,
} from "../../shared/api/types";
import { useProfileQuery, useUpdateProfileMutation } from "./useProfilesQuery";
import { ProfileForm } from "./ProfileForm";
import { SharedProfileBanners } from "./SharedProfileBanners";

function pickMetadata(values: ProfileUpdateRequest): ProfileUpdateRequest {
  return {
    name: values.name,
    notes: values.notes,
    sort_order: values.sort_order,
    group_id: values.group_id,
  };
}

export function ConfigTab({ profileId }: { profileId: string }) {
  const { t } = useI18n();
  const client = useApiClient();
  const { data: profile } = useProfileQuery(profileId, client);
  const updateMutation = useUpdateProfileMutation(client);
  const [runtimeDirty, setRuntimeDirty] = useState(false);
  const [formKey, setFormKey] = useState(0);
  const onDirtyRuntimeConfig = useCallback(
    (changed: boolean) => setRuntimeDirty(changed),
    [],
  );

  const handleSubmit = async (
    values: ProfileCreateRequest | ProfileUpdateRequest,
  ) => {
    const data = runtimeDirty
      ? (values as ProfileUpdateRequest)
      : pickMetadata(values as ProfileUpdateRequest);
    await updateMutation.mutateAsync({ id: profileId, data });
    setRuntimeDirty(false);
    setFormKey((key) => key + 1);
  };

  return (
    <div data-testid="profile-config-tab" className="flex flex-col gap-md">
      <SharedProfileBanners profileId={profileId} />
      {profile && (
        <ProfileForm
          key={formKey}
          mode="edit"
          initial={profile}
          onSubmit={handleSubmit}
          submitLabel={t("formSave")}
          onDirtyRuntimeConfig={onDirtyRuntimeConfig}
        />
      )}
    </div>
  );
}
