import { useState } from 'react';
import { ArrowDown, ArrowUp } from 'lucide-react';
import { useI18n } from '../../i18n';
import { ApiError } from '../../shared/api/client';
import { useApiClient } from '../../shared/api/client_context';
import type { GroupResponse } from '../../shared/api/types';
import {
  Banner,
  Button,
  Dialog,
  GroupChip,
  IconButton,
  Input,
} from '../../shared/ui';
import { GroupColorPicker } from './GroupColorPicker';
import { useGroupReorder } from './useGroupReorder';
import {
  useCreateGroupMutation,
  useDeleteGroupMutation,
  useGroupsQuery,
  useProfilesQuery,
  useUpdateGroupMutation,
} from './useProfilesQuery';

type EditState = { id: string; kind: 'rename' | 'color' } | null;

export function GroupManagerDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useI18n();
  const client = useApiClient();
  const { data: groups } = useGroupsQuery(client);
  const { data: profiles } = useProfilesQuery(client);
  const createMutation = useCreateGroupMutation(client);
  const updateMutation = useUpdateGroupMutation(client);
  const deleteMutation = useDeleteGroupMutation(client);
  const { items, moveUp, moveDown, reorder } = useGroupReorder(groups);

  const [newName, setNewName] = useState('');
  const [newColor, setNewColor] = useState<GroupResponse['color']>('slate');
  const [edit, setEdit] = useState<EditState>(null);
  const [draftName, setDraftName] = useState('');
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function handleError(err: unknown) {
    if (err instanceof ApiError) {
      setError(err.errorCode ? `${err.message} (${err.errorCode})` : err.message);
    } else {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function countFor(id: string) {
    return (profiles ?? []).filter((profile) => profile.group_id === id).length;
  }

  async function handleCreate() {
    const name = newName.trim();
    if (!name) return;
    try {
      await createMutation.mutateAsync({
        name,
        color: newColor,
        sort_order: items.length,
      });
      setNewName('');
      setNewColor('slate');
      setError(null);
    } catch (err) {
      handleError(err);
    }
  }

  async function submitRename(id: string) {
    const name = draftName.trim();
    if (!name) return;
    try {
      await updateMutation.mutateAsync({ groupId: id, data: { name } });
      setEdit(null);
      setError(null);
    } catch (err) {
      handleError(err);
    }
  }

  async function submitColor(id: string, color: GroupResponse['color']) {
    try {
      await updateMutation.mutateAsync({ groupId: id, data: { color } });
      setEdit(null);
      setError(null);
    } catch (err) {
      handleError(err);
    }
  }

  async function confirmDelete(id: string) {
    try {
      await deleteMutation.mutateAsync(id);
      setDeleteId(null);
      setError(null);
    } catch (err) {
      handleError(err);
    }
  }

  function handleDrop(targetId: string) {
    const sourceId = draggedId;
    setDraggedId(null);
    if (!sourceId || sourceId === targetId) return;
    const ids = items.map((group) => group.id);
    const from = ids.indexOf(sourceId);
    const to = ids.indexOf(targetId);
    if (from < 0 || to < 0) return;
    ids.splice(from, 1);
    ids.splice(to, 0, sourceId);
    void reorder(ids).catch(handleError);
  }

  return (
    <Dialog
      trigger={<span />}
      title={t('groupManagerTitle')}
      open={open}
      onOpenChange={onOpenChange}
    >
      <div
        data-testid="group-manager-dialog"
        className="flex flex-col gap-md"
      >
        {error && (
          <Banner
            tone="danger"
            testId="group-manager-error"
            onDismiss={() => setError(null)}
          >
            {error}
          </Banner>
        )}

        <div className="flex flex-wrap items-end gap-sm">
          <Input
            data-testid="group-new-name"
            aria-label={t('groupNew')}
            placeholder={t('groupNew')}
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
          />
          <div data-testid="group-new-color">
            <GroupColorPicker value={newColor} onChange={setNewColor} />
          </div>
          <Button
            data-testid="group-create-submit"
            variant="primary"
            disabled={newName.trim().length === 0 || createMutation.isPending}
            onClick={() => void handleCreate()}
          >
            {t('groupNew')}
          </Button>
        </div>

        <p className="font-ui text-label-sm text-on-surface-muted">
          {t('groupKeyboardHint')}
        </p>

        <ul className="flex flex-col gap-sm">
          {items.map((group) => {
            const count = countFor(group.id);
            const renaming = edit?.id === group.id && edit.kind === 'rename';
            const coloring = edit?.id === group.id && edit.kind === 'color';
            return (
              <li
                key={group.id}
                data-testid="group-row"
                draggable
                tabIndex={0}
                onDragStart={() => setDraggedId(group.id)}
                onDragOver={(event) => event.preventDefault()}
                onDrop={() => handleDrop(group.id)}
                onKeyDown={(event) => {
                  if (event.key === 'ArrowUp') {
                    event.preventDefault();
                    void moveUp(group.id).catch(handleError);
                  } else if (event.key === 'ArrowDown') {
                    event.preventDefault();
                    void moveDown(group.id).catch(handleError);
                  }
                }}
                className="flex flex-wrap items-center gap-sm rounded-md border border-outline bg-surface-subtle px-md py-sm"
              >
                <GroupChip label={group.name} hue={group.color} />
                <span
                  data-testid="group-used-by"
                  className="font-ui text-label-sm text-on-surface-muted"
                >
                  {t('groupUsedBy', { count })}
                </span>

                {renaming ? (
                  <>
                    <Input
                      data-testid="group-rename-input"
                      aria-label={t('groupRename')}
                      value={draftName}
                      onChange={(event) => setDraftName(event.target.value)}
                    />
                    <Button
                      data-testid="group-rename-save"
                      size="sm"
                      variant="primary"
                      disabled={updateMutation.isPending}
                      onClick={() => void submitRename(group.id)}
                    >
                      {t('groupSave')}
                    </Button>
                    <Button size="sm" onClick={() => setEdit(null)}>
                      {t('groupCancel')}
                    </Button>
                  </>
                ) : coloring ? (
                  <>
                    <GroupColorPicker
                      value={group.color}
                      onChange={(color) => void submitColor(group.id, color)}
                    />
                    <Button size="sm" onClick={() => setEdit(null)}>
                      {t('groupCancel')}
                    </Button>
                  </>
                ) : (
                  <>
                    <Button
                      data-testid="group-rename-open"
                      size="sm"
                      onClick={() => {
                        setEdit({ id: group.id, kind: 'rename' });
                        setDraftName(group.name);
                      }}
                    >
                      {t('groupRename')}
                    </Button>
                    <Button
                      data-testid="group-color-open"
                      size="sm"
                      onClick={() => setEdit({ id: group.id, kind: 'color' })}
                    >
                      {t('groupColor')}
                    </Button>
                  </>
                )}

                <IconButton
                  data-testid="group-reorder-up"
                  label={t('groupReorderUp')}
                  onClick={() => void moveUp(group.id).catch(handleError)}
                >
                  <ArrowUp aria-hidden="true" className="size-(--component-icon-md-size)" />
                </IconButton>
                <IconButton
                  data-testid="group-reorder-down"
                  label={t('groupReorderDown')}
                  onClick={() => void moveDown(group.id).catch(handleError)}
                >
                  <ArrowDown aria-hidden="true" className="size-(--component-icon-md-size)" />
                </IconButton>
                <Button
                  data-testid="group-delete-open"
                  size="sm"
                  variant="danger"
                  onClick={() => setDeleteId(group.id)}
                >
                  {t('groupDelete')}
                </Button>

                {deleteId === group.id && (
                  <div
                    data-testid="group-delete-confirm"
                    className="flex w-full flex-col gap-sm"
                  >
                    <Banner tone="danger">
                      {t('groupDeleteConfirm', { count })}
                    </Banner>
                    <div className="flex flex-wrap items-center gap-sm">
                      <span
                        data-testid="group-affected-count"
                        className="font-ui text-label-sm text-on-surface-muted"
                      >
                        {t('groupAffectedCount', { count })}
                      </span>
                      <Button
                        data-testid="group-delete-accept"
                        size="sm"
                        variant="danger"
                        disabled={deleteMutation.isPending}
                        onClick={() => void confirmDelete(group.id)}
                      >
                        {t('groupDelete')}
                      </Button>
                      <Button
                        data-testid="group-delete-cancel"
                        size="sm"
                        onClick={() => setDeleteId(null)}
                      >
                        {t('groupCancel')}
                      </Button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </Dialog>
  );
}
