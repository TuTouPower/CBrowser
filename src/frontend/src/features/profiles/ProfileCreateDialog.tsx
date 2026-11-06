import { Dialog } from "../../shared/ui";
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

  const handleSubmit = async (
    values: ProfileCreateRequest | ProfileUpdateRequest,
  ) => {
    const { __startAfterCreate, ...createData } =
      values as ProfileCreateRequest & { __startAfterCreate?: boolean };
    const created = await createMutation.mutateAsync(
      createData as ProfileCreateRequest,
    );
    if (__startAfterCreate) {
      await setDesiredStateMutation.mutateAsync({
        id: created.id,
        state: "running",
      });
    }
    onOpenChange(false);
  };

  return (
    <Dialog
      trigger={<span />}
      title={t("envNew")}
      open={open}
      onOpenChange={onOpenChange}
      contentClassName="max-h-dialog-height overflow-y-auto"
    >
      <div data-testid="env-new-dialog">
        <ProfileForm
          mode="create"
          onSubmit={handleSubmit}
          submitLabel={t("formCreate")}
        />
      </div>
    </Dialog>
  );
}
