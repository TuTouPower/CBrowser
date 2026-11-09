import { useState } from "react";
import { Banner, Dialog } from "../../shared/ui";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import type {
  ProfileCreateRequest,
  ProfileUpdateRequest,
} from "../../shared/api/types";
import {
  useCreateProfileMutation,
  useSetDesiredStateMutation,
} from "./useProfilesQuery";
import { ProfileForm } from "./ProfileForm";

export function ProfileCreateDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useI18n();
  const client = useApiClient();
  const createMutation = useCreateProfileMutation(client);
  const setDesiredStateMutation = useSetDesiredStateMutation(client);
  const [createError, setCreateError] = useState<string | null>(null);
  // P1-13: pending 合并禁用，防双击重复创建。
  const isPending =
    createMutation.isPending || setDesiredStateMutation.isPending;

  const handleOpenChange = (open: boolean) => {
    if (open) setCreateError(null);
    onOpenChange(open);
  };

  const handleSubmit = async (
    values: ProfileCreateRequest | ProfileUpdateRequest,
  ) => {
    setCreateError(null);
    const { __startAfterCreate, ...createData } =
      values as ProfileCreateRequest & { __startAfterCreate?: boolean };
    let created;
    try {
      created = await createMutation.mutateAsync(
        createData as ProfileCreateRequest,
      );
    } catch (err) {
      const reason =
        err instanceof Error ? err.message : String(err ?? t("failedToCreateProfile"));
      setCreateError(`${t("failedToCreateProfile")}: ${reason}`);
      return;
    }
    if (__startAfterCreate) {
      try {
        await setDesiredStateMutation.mutateAsync({
          id: created.id,
          state: "running",
        });
      } catch (err) {
        // P1-13: 创建成 + 启动败必须提示已创建 id，不吞错、不关窗。
        const reason = err instanceof Error ? err.message : String(err);
        setCreateError(
          `Profile ${created.id} created, but start failed: ${reason}`,
        );
        return;
      }
    }
    setCreateError(null);
    onOpenChange(false);
  };

  return (
    <Dialog
      trigger={<span />}
      title={t("envNew")}
      open={open}
      onOpenChange={handleOpenChange}
      contentClassName="max-h-dialog-height overflow-y-auto"
    >
      <div data-testid="env-new-dialog" className="flex flex-col gap-md">
        {createError ? (
          <Banner tone="danger" testId="env-new-error">
            {createError}
          </Banner>
        ) : null}
        <ProfileForm
          mode="create"
          onSubmit={handleSubmit}
          submitLabel={t("formCreate")}
          isPending={isPending}
        />
      </div>
    </Dialog>
  );
}
