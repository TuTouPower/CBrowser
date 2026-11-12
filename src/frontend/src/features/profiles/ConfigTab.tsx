import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import type {
  ProfileCreateRequest,
  ProfileUpdateRequest,
} from "../../shared/api/types";
import {
  profileKeys,
  useProfileQuery,
  useUpdateProfileMutation,
} from "./useProfilesQuery";
import { ProfileForm } from "./ProfileForm";
import { SharedProfileBanners } from "./SharedProfileBanners";

export function ConfigTab({ profileId }: { profileId: string }) {
  const { t } = useI18n();
  const client = useApiClient();
  const queryClient = useQueryClient();
  const { data: profile } = useProfileQuery(profileId, client);
  const updateMutation = useUpdateProfileMutation(client);
  const [formKey, setFormKey] = useState(0);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const handleSubmit = async (
    values: ProfileCreateRequest | ProfileUpdateRequest,
  ) => {
    setSaveError(null);
    setSaveSuccess(false);
    // t058 A24: the form already submits only the fields that changed,
    // so the payload is forwarded as-is — no metadata/runtime split here.
    const data = values as ProfileUpdateRequest;
    // P2: 保存失败 catch，避免 unhandled rejection；成功回显。
    let saved;
    try {
      saved = await updateMutation.mutateAsync({ id: profileId, data });
    } catch (err) {
      const reason = err instanceof Error ? err.message : String(err);
      setSaveError(t("formSaveFailed", { error: reason }));
      return;
    }
    // P1-12: 先用返回值写缓存，再 formKey+1 remount，不再回显旧值覆盖。
    queryClient.setQueryData(profileKeys.detail(profileId), saved);
    setSaveSuccess(true);
    setFormKey((key) => key + 1);
  };

  return (
    <div data-testid="profile-config-tab" className="flex flex-col gap-md">
      <SharedProfileBanners profileId={profileId} />
      {saveError ? (
        <div
          data-testid="profile-config-save-error"
          role="alert"
          className="font-ui text-label-sm text-danger"
        >
          {saveError}
        </div>
      ) : null}
      {saveSuccess ? (
        <div
          data-testid="profile-config-save-success"
          className="font-ui text-label-sm text-on-surface"
        >
          {t("profileUpdatedSuccessfully")}
        </div>
      ) : null}
      {profile && (
        <ProfileForm
          key={formKey}
          mode="edit"
          initial={profile}
          onSubmit={handleSubmit}
          submitLabel={t("formSave")}
        />
      )}
    </div>
  );
}
