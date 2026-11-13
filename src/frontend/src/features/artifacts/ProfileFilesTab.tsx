import { useRef, useState } from 'react';
import { Download, FolderArchive, Trash2, Upload } from 'lucide-react';
import { useI18n } from '../../i18n';
import { useApiClient } from '../../shared/api/client_context';
import { Banner, Button, EmptyState, IconButton } from '../../shared/ui';
import {
  useArtifactsQuery,
  useDeleteArtifactMutation,
  useUploadArtifactMutation,
} from './useArtifacts';

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
}

export function ProfileFilesTab({ profileId }: { profileId: string }) {
  const { t } = useI18n();
  const client = useApiClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const artifacts = useArtifactsQuery(profileId, client);
  const uploadMutation = useUploadArtifactMutation(profileId, client);
  const deleteMutation = useDeleteArtifactMutation(profileId, client);

  const pickFiles = async (list: FileList | null) => {
    const files = list ? Array.from(list) : [];
    if (inputRef.current) inputRef.current.value = '';
    if (files.length === 0) return;
    setError(null);
    setNotice(null);
    for (const [index, file] of files.entries()) {
      try {
        await uploadMutation.mutateAsync(file);
      } catch (err) {
        setError(
          t('uploadPartialFailure', {
            succeeded: index,
            name: file.name,
            remaining: files.length - index - 1,
            error: err instanceof Error ? err.message : t('uploadFailed'),
          }),
        );
        return;
      }
    }
    setNotice(t('artifactsUploaded', { count: files.length }));
  };

  const remove = async (artifactId: string) => {
    if (!window.confirm(t('deleteArtifactConfirm'))) return;
    setError(null);
    setNotice(null);
    try {
      await deleteMutation.mutateAsync(artifactId);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('deleteFailed'));
    }
  };

  return (
    <div data-testid="profile-files-tab" className="flex flex-col gap-lg">
      <div className="flex items-start justify-between gap-md">
        <div className="min-w-none">
          <h2 className="flex items-center gap-sm font-ui text-headline-md text-on-surface">
            <FolderArchive aria-hidden="true" className="size-(--component-icon-lg-size) text-accent" />
            {t('profileFiles')}
          </h2>
          <p className="mt-xs font-ui text-body-sm text-on-surface-muted">
            {t('profileFilesHint')}
          </p>
        </div>
        <div className="flex items-center gap-sm">
          <input
            ref={inputRef}
            type="file"
            multiple
            className="hidden"
            data-testid="artifact-upload-input"
            onChange={(event) => void pickFiles(event.target.files)}
          />
          <Button
            data-testid="artifact-upload"
            variant="primary"
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={uploadMutation.isPending}
          >
            <Upload aria-hidden="true" className="size-(--component-icon-sm-size)" />
            {uploadMutation.isPending ? t('uploading') : t('uploadAFile')}
          </Button>
        </div>
      </div>

      {error && (
        <Banner tone="danger" testId="artifact-error">
          {error}
        </Banner>
      )}
      {notice && (
        <div
          data-testid="artifact-success"
          role="status"
          className="rounded-md border border-outline bg-surface-subtle px-md py-sm font-ui text-body-sm text-on-surface"
        >
          {notice}
        </div>
      )}

      {artifacts.isLoading ? (
        <div className="rounded-lg border border-outline bg-surface px-md py-2xl text-center font-ui text-body-sm text-on-surface-muted">
          {t('loading')}
        </div>
      ) : artifacts.error ? (
        <Banner tone="danger" testId="artifact-list-error">
          {artifacts.error.message || t('failedToListFiles')}
        </Banner>
      ) : (artifacts.data ?? []).length === 0 ? (
        <EmptyState
          title={t('profileFiles')}
          description={t('noFilesYet')}
          icon={<FolderArchive aria-hidden="true" className="size-(--component-icon-2xl-size)" />}
        />
      ) : (
        <ul className="overflow-hidden rounded-lg border border-outline">
          {(artifacts.data ?? []).map((artifact) => (
            <li
              key={artifact.id}
              data-testid="artifact-item"
              className="flex items-center gap-md border-b border-outline bg-surface px-md py-sm last:border-b-0 hover:bg-surface-hover"
            >
              <div className="min-w-none flex-1">
                <div className="truncate font-ui text-body-md text-on-surface">
                  {artifact.name}
                </div>
                <div className="truncate font-mono text-mono-md text-on-surface-muted">
                  {artifact.kind === 'download'
                    ? t('downloadedByBrowser')
                    : t('uploaded')}
                  {' · '}
                  {formatSize(artifact.size)}
                  {' · '}
                  {new Date(artifact.created_at).toLocaleString()}
                  {' · '}
                  {artifact.container_path ?? ''}
                </div>
              </div>
              <a
                data-testid="artifact-download"
                href={client.artifacts.downloadUrl(profileId, artifact.id)}
                download={artifact.name}
                aria-label={t('downloadToComputer')}
                className="inline-flex h-(--component-icon-button-height) w-(--component-icon-button-width) shrink-0 items-center justify-center rounded-md bg-surface text-on-surface hover:bg-surface-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
              >
                <Download aria-hidden="true" className="size-(--component-icon-md-size)" />
              </a>
              <IconButton
                data-testid="artifact-delete"
                label={t('removeFromProfile')}
                onClick={() => void remove(artifact.id)}
                disabled={deleteMutation.isPending}
              >
                <Trash2 aria-hidden="true" className="size-(--component-icon-md-size)" />
              </IconButton>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
