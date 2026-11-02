import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Download, FolderArchive, Trash2, Upload } from "lucide-react";
import { useI18n } from "../../i18n";
import { useProfileQuery } from "../profiles/useProfilesQuery";
import {
  useArtifactsQuery,
  useDeleteArtifactMutation,
  useUploadArtifactMutation,
} from "./useArtifacts";
import { defaultApiClient } from "../../shared/api/client";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
}

export function ProfileFilesPage() {
  const { profileId } = useParams<{ profileId: string }>();
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const { data: profile } = useProfileQuery(profileId);
  const artifacts = useArtifactsQuery(profileId);
  const uploadMutation = useUploadArtifactMutation(profileId);
  const deleteMutation = useDeleteArtifactMutation(profileId);

  const pickFiles = async (list: FileList | null) => {
    const files = list ? Array.from(list) : [];
    if (inputRef.current) inputRef.current.value = "";
    if (files.length === 0) return;
    setError(null);
    setNotice(null);
    for (const file of files) {
      try {
        await uploadMutation.mutateAsync(file);
      } catch (err) {
        setError(err instanceof Error ? err.message : t("uploadFailed"));
        return;
      }
    }
    setNotice(t("artifactsUploaded", { count: files.length }));
  };

  const remove = async (artifactId: string) => {
    if (!window.confirm(t("deleteArtifactConfirm"))) return;
    setError(null);
    setNotice(null);
    try {
      await deleteMutation.mutateAsync(artifactId);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("deleteFailed"));
    }
  };

  if (!profileId) {
    return <div className="p-8 text-gray-400 text-sm">{t("profileNotFoundOrFailed")}</div>;
  }

  return (
    <div data-testid="profile-files-page" className="p-8 max-w-3xl mx-auto">
      <Link
        to={`/?profileId=${profileId}`}
        className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 mb-6"
      >
        <ArrowLeft className="h-4 w-4" />
        {t("backToSession")}
      </Link>

      <div className="bg-surface-1 border border-border rounded-lg p-6">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div>
            <h1 className="text-lg font-bold text-gray-100 flex items-center gap-2">
              <FolderArchive className="h-5 w-5 text-primary" />
              {t("profileFiles")}
            </h1>
            <p className="text-xs text-gray-400 mt-1">
              {profile ? profile.name : profileId} — {t("profileFilesHint")}
            </p>
          </div>
          <div>
            <input
              ref={inputRef}
              type="file"
              multiple
              className="hidden"
              data-testid="artifact-file-input"
              onChange={(event) => void pickFiles(event.target.files)}
            />
            <button
              type="button"
              data-testid="artifact-upload-button"
              onClick={() => inputRef.current?.click()}
              disabled={uploadMutation.isPending}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-xs bg-primary text-white hover:opacity-90 disabled:opacity-50"
            >
              <Upload className="h-3.5 w-3.5" />
              {uploadMutation.isPending ? t("uploading") : t("uploadAFile")}
            </button>
          </div>
        </div>

        {error && (
          <div role="alert" className="mb-3 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded p-2">
            {error}
          </div>
        )}
        {notice && (
          <div data-testid="artifact-notice" className="mb-3 text-xs text-green-400 bg-green-500/10 border border-green-500/20 rounded p-2">
            {notice}
          </div>
        )}

        {artifacts.isLoading ? (
          <div className="py-8 text-center text-sm text-gray-400">{t("loading")}</div>
        ) : artifacts.error ? (
          <div role="alert" className="py-8 text-center text-sm text-red-400">
            {artifacts.error.message || t("failedToListFiles")}
          </div>
        ) : (artifacts.data ?? []).length === 0 ? (
          <div data-testid="artifact-empty" className="py-10 text-center text-sm text-gray-400">
            {t("noFilesYet")}
          </div>
        ) : (
          <ul className="divide-y divide-border border border-border rounded overflow-hidden">
            {(artifacts.data ?? []).map((artifact) => (
              <li
                key={artifact.id}
                data-testid="artifact-row"
                className="flex items-center gap-3 px-3 py-2.5 bg-surface-2/40"
              >
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-gray-100 truncate">{artifact.name}</div>
                  <div className="text-[11px] text-gray-400 truncate">
                    {artifact.kind === "download"
                      ? t("downloadedByBrowser")
                      : t("uploaded")}
                    {" · "}
                    {formatSize(artifact.size)}
                    {" · "}
                    {artifact.container_path}
                  </div>
                </div>
                <a
                  href={defaultApiClient.artifacts.downloadUrl(profileId, artifact.id)}
                  download={artifact.name}
                  className="p-1.5 rounded text-gray-300 hover:text-primary hover:bg-surface-3"
                  aria-label={t("downloadToComputer")}
                  title={t("downloadToComputer")}
                >
                  <Download className="h-4 w-4" />
                </a>
                <button
                  type="button"
                  onClick={() => void remove(artifact.id)}
                  disabled={deleteMutation.isPending}
                  className="p-1.5 rounded text-gray-300 hover:text-red-400 hover:bg-red-500/10 disabled:opacity-50"
                  aria-label={t("removeFromProfile")}
                  title={t("removeFromProfile")}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
