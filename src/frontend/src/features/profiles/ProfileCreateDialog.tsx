import { useState } from "react";
import { Banner, Button, Dialog } from "../../shared/ui";
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
  // P1-F: 创建成功 + 启动失败后记住 created.id，主按钮切“重试启动/关闭”，
  // 重试只调 setDesiredState，不再重复 create（同名 409/改名多建消失）。
  const [createdId, setCreatedId] = useState<string | null>(null);
  // P1-13: pending 合并禁用，防双击重复创建。
  const isPending =
    createMutation.isPending || setDesiredStateMutation.isPending;

  const handleOpenChange = (nextOpen: boolean) => {
    if (nextOpen) {
      setCreateError(null);
      setCreatedId(null);
    } else {
      setCreatedId(null);
    }
    onOpenChange(nextOpen);
  };

  const handleClose = () => {
    setCreateError(null);
    setCreatedId(null);
    onOpenChange(false);
  };

  const handleRetryStart = async () => {
    if (!createdId) return;
    setCreateError(null);
    try {
      await setDesiredStateMutation.mutateAsync({
        id: createdId,
        state: "running",
      });
    } catch (err) {
      const reason = err instanceof Error ? err.message : String(err);
      setCreateError(
        t("profileCreateStartFailed", { id: createdId, error: reason })
      );
      return;
    }
    setCreateError(null);
    setCreatedId(null);
    onOpenChange(false);
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
        // P1-F: 错误文案入 i18n，记住 id 切重试，不关窗。
        const reason = err instanceof Error ? err.message : String(err);
        setCreatedId(created.id);
        setCreateError(
          t("profileCreateStartFailed", { id: created.id, error: reason })
        );
        return;
      }
    }
    setCreateError(null);
    setCreatedId(null);
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
        {createdId ? (
          <div className="flex justify-end gap-sm">
            <Button
              data-testid="env-new-retry-start"
              variant="primary"
              disabled={isPending}
              onClick={() => void handleRetryStart()}
            >
              {t("profileCreateRetryStart")}
            </Button>
            <Button
              data-testid="env-new-close"
              variant="secondary"
              onClick={handleClose}
            >
              {t("profileCreateClose")}
            </Button>
          </div>
        ) : (
          <ProfileForm
            mode="create"
            onSubmit={handleSubmit}
            submitLabel={t("formCreate")}
            isPending={isPending}
          />
        )}
      </div>
    </Dialog>
  );
}
