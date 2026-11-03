import { useState, useEffect, useRef, type FormEvent } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { ArrowLeft, Copy, Cpu, FolderArchive, RotateCcw, Trash2 } from "lucide-react";
import {
  useProfileQuery,
  useProfileRuntimeQuery,
  useUpdateProfileMutation,
  useDeleteProfileMutation,
  useApplyDisplaySettingsMutation,
  useDuplicateProfileMutation,
  useResetProfileMutation,
} from "./useProfilesQuery";
import { useI18n } from "../../i18n";

export function ProfileDetailPage() {
  const { profileId } = useParams<{ profileId: string }>();
  const { t } = useI18n();
  const navigate = useNavigate();

  const { data: profile, isLoading, error: loadError } = useProfileQuery(profileId);
  const { data: runtime } = useProfileRuntimeQuery(profileId);
  const updateMutation = useUpdateProfileMutation();
  const deleteMutation = useDeleteProfileMutation();
  const applyDisplayMutation = useApplyDisplaySettingsMutation();
  const duplicateMutation = useDuplicateProfileMutation();
  const resetMutation = useResetProfileMutation();

  const [duplicateOpen, setDuplicateOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [name, setName] = useState("");
  const [proxy, setProxy] = useState("");
  const [screenWidth, setScreenWidth] = useState(1920);
  const [screenHeight, setScreenHeight] = useState(1080);
  const [tagsInput, setTagsInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const dirtyFields = useRef<Set<string>>(new Set());

  useEffect(() => {
    dirtyFields.current.clear();
  }, [profileId]);

  useEffect(() => {
    if (!profile) return;
    const dirty = dirtyFields.current;
    if (!dirty.has("name")) setName(profile.name || "");
    if (!dirty.has("proxy")) setProxy(profile.proxy || "");
    if (!dirty.has("geometry")) {
      setScreenWidth(profile.screen_width || 1920);
      setScreenHeight(profile.screen_height || 1080);
    }
    if (!dirty.has("tags")) {
      setTagsInput(
        profile.tags
          ? profile.tags.map((t) => (typeof t === "string" ? t : t.tag)).join(", ")
          : "",
      );
    }
  }, [profile]);

  const markDirty = (field: string) => {
    dirtyFields.current.add(field);
  };

  const runtimeRunning = runtime
    ? !(runtime.desired_state === "stopped" && runtime.observed_state === "stopped")
    : false;

  const handleDuplicate = async (includeBrowserState: boolean) => {
    if (!profileId) return;
    setError(null);
    try {
      const clone = await duplicateMutation.mutateAsync({
        id: profileId,
        includeBrowserState,
      });
      navigate(`/profiles/${clone.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("failedToDuplicateProfile"));
    }
  };

  const handleReset = async () => {
    if (!profileId) return;
    setError(null);
    try {
      await resetMutation.mutateAsync(profileId);
      setResetOpen(false);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 2000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("failedToResetProfile"));
    }
  };

  const displayPending = Boolean(
    profile &&
      runtime?.observed_state === "running" &&
      runtime.config_version !== profile.current_config_version,
  );

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!profileId || !name.trim()) return;

    setError(null);
    setSuccess(false);

    try {
      const tags = tagsInput
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean)
        .map((t) => ({ tag: t }));

      await updateMutation.mutateAsync({
        id: profileId,
        data: {
          name: name.trim(),
          proxy: proxy.trim() || null,
          screen_width: screenWidth,
          screen_height: screenHeight,
          tags,
        },
      });

      dirtyFields.current.clear();
      setSuccess(true);
      setTimeout(() => setSuccess(false), 2000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("failedToUpdateProfile"));
    }
  };

  const handleDelete = async () => {
    if (!profileId) return;
    if (!window.confirm(t("deleteProfileConfirm"))) return;

    try {
      await deleteMutation.mutateAsync(profileId);
      navigate("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("failedToDeleteProfile"));
    }
  };

  if (isLoading) {
    return (
      <div className="p-8 text-center text-gray-400 text-sm">
        {t("loading")}
      </div>
    );
  }

  if (loadError || !profile) {
    return (
      <div className="p-8 max-w-2xl mx-auto">
        <Link to="/" className="inline-flex items-center gap-1.5 text-xs text-gray-400 mb-4">
          <ArrowLeft className="h-4 w-4" /> {t("backToDashboard")}
        </Link>
        <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded text-sm">
          {t("profileNotFoundOrFailed")}
        </div>
      </div>
    );
  }

  return (
    <div data-testid="profile-detail-page" className="p-8 max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <Link
          to={`/?profileId=${profile.id}`}
          className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200"
        >
          <ArrowLeft className="h-4 w-4" />
          {t("backToSession")}
        </Link>

        <div className="flex items-center gap-2">
          <Link
            to={`/profiles/${profile.id}/files`}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded text-xs bg-surface-2 hover:bg-surface-3 text-gray-300 border border-border"
          >
            <FolderArchive className="h-3.5 w-3.5" />
            {t("files")}
          </Link>
          <Link
            to={`/automation/${profile.id}`}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded text-xs bg-surface-2 hover:bg-surface-3 text-gray-300 border border-border"
          >
            <Cpu className="h-3.5 w-3.5" />
            {t("automation")}
          </Link>
          <button
            type="button"
            data-testid="profile-duplicate-button"
            onClick={() => {
              setDuplicateOpen((open) => !open);
              setResetOpen(false);
            }}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded text-xs bg-surface-2 hover:bg-surface-3 text-gray-300 border border-border"
          >
            <Copy className="h-3.5 w-3.5" />
            {t("duplicate")}
          </button>
          <button
            type="button"
            data-testid="profile-reset-button"
            onClick={() => {
              setResetOpen((open) => !open);
              setDuplicateOpen(false);
            }}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded text-xs bg-surface-2 hover:bg-surface-3 text-gray-300 border border-border"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            {t("reset")}
          </button>
        </div>
      </div>

      {duplicateOpen && (
        <div
          data-testid="profile-duplicate-panel"
          className="mb-4 bg-surface-1 border border-border rounded-lg p-4"
        >
          <h2 className="text-sm font-semibold text-gray-100 mb-1">
            {t("duplicateProfileTitle")}
          </h2>
          <p className="text-xs text-gray-400 mb-3">{t("duplicateProfileHint")}</p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void handleDuplicate(false)}
              disabled={duplicateMutation.isPending}
              className="px-3 py-1.5 rounded text-xs bg-primary text-white disabled:opacity-50"
            >
              {t("duplicateSettingsOnly")}
            </button>
            <button
              type="button"
              onClick={() => void handleDuplicate(true)}
              disabled={duplicateMutation.isPending || runtimeRunning}
              className="px-3 py-1.5 rounded text-xs bg-surface-2 border border-border text-gray-200 disabled:opacity-50"
              title={runtimeRunning ? t("stopProfileFirst") : undefined}
            >
              {t("duplicateWithStateTitle")}
            </button>
            <button
              type="button"
              onClick={() => setDuplicateOpen(false)}
              className="px-3 py-1.5 rounded text-xs text-gray-400 hover:text-gray-200"
            >
              {t("cancel")}
            </button>
          </div>
          {runtimeRunning && (
            <p className="text-[11px] text-yellow-400 mt-2">{t("stopProfileFirst")}</p>
          )}
        </div>
      )}

      {resetOpen && (
        <div
          data-testid="profile-reset-panel"
          className="mb-4 bg-red-500/5 border border-red-500/30 rounded-lg p-4"
        >
          <h2 className="text-sm font-semibold text-red-300 mb-1">{t("resetProfileTitle")}</h2>
          <p className="text-xs text-gray-300 mb-1">{t("resetProfileDataList")}</p>
          <p className="text-xs text-gray-400 mb-3">{t("resetProfileKeeps")}</p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void handleReset()}
              disabled={resetMutation.isPending || runtimeRunning}
              className="px-3 py-1.5 rounded text-xs bg-red-500 text-white disabled:opacity-50"
            >
              {resetMutation.isPending ? t("resetting") : t("reset")}
            </button>
            <button
              type="button"
              onClick={() => setResetOpen(false)}
              className="px-3 py-1.5 rounded text-xs text-gray-400 hover:text-gray-200"
            >
              {t("cancel")}
            </button>
          </div>
          {runtimeRunning && (
            <p className="text-[11px] text-yellow-400 mt-2">{t("stopProfileFirst")}</p>
          )}
        </div>
      )}

      <div className="bg-surface-1 border border-border rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-lg font-bold text-gray-100">{t("editProfile")}</h1>
          <button
            type="button"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 border border-red-500/20 transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
            {t("delete")}
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 text-red-400 text-xs rounded">
            {error}
          </div>
        )}

        {success && (
          <div
            data-testid="profile-save-success"
            className="mb-4 p-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs rounded"
          >
            {t("profileUpdatedSuccessfully")}
          </div>
        )}

        {displayPending && (
          <div
            data-testid="profile-display-pending"
            className="mb-4 p-3 bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs rounded flex items-center justify-between gap-3"
          >
            <span>{t("displaySettingsSavedPending")}</span>
            <button
              type="button"
              data-testid="profile-display-apply-btn"
              onClick={() => profileId && applyDisplayMutation.mutate(profileId)}
              disabled={applyDisplayMutation.isPending}
              className="px-3 py-1.5 rounded bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 disabled:opacity-50 shrink-0"
            >
              {applyDisplayMutation.isPending
                ? t("displayApplyingRestart")
                : t("displayApplyAndRestart")}
            </button>
          </div>
        )}

        {applyDisplayMutation.error && (
          <div
            data-testid="profile-display-apply-error"
            role="alert"
            className="mb-4 p-3 bg-red-500/10 border border-red-500/20 text-red-400 text-xs rounded"
          >
            {t("displayApplyFailed", {
              error: applyDisplayMutation.error.message,
            })}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1.5">
              {t("profileName")} *
            </label>
            <input
              data-testid="profile-name-input"
              type="text"
              required
              value={name}
              onChange={(e) => { markDirty("name"); setName(e.target.value); }}
              className="w-full px-3 py-2 bg-surface-2 border border-border rounded text-sm text-gray-200 focus:outline-none focus:border-primary"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1.5">
              {t("proxyUrl")}
            </label>
            <input
              type="text"
              value={proxy}
              onChange={(e) => { markDirty("proxy"); setProxy(e.target.value); }}
              placeholder="http://user:pass@host:port"
              className="w-full px-3 py-2 bg-surface-2 border border-border rounded text-sm text-gray-200 focus:outline-none focus:border-primary"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-300 mb-1.5">
                {t("widthPx")}
              </label>
              <input
                data-testid="profile-width-input"
                type="number"
                value={screenWidth}
                onChange={(e) => { markDirty("geometry"); setScreenWidth(Number(e.target.value)); }}
                className="w-full px-3 py-2 bg-surface-2 border border-border rounded text-sm text-gray-200 focus:outline-none focus:border-primary"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-300 mb-1.5">
                {t("heightPx")}
              </label>
              <input
                data-testid="profile-height-input"
                type="number"
                value={screenHeight}
                onChange={(e) => { markDirty("geometry"); setScreenHeight(Number(e.target.value)); }}
                className="w-full px-3 py-2 bg-surface-2 border border-border rounded text-sm text-gray-200 focus:outline-none focus:border-primary"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1.5">
              {t("tagsCommaSeparated")}
            </label>
            <input
              data-testid="profile-tags-input"
              type="text"
              value={tagsInput}
              onChange={(e) => { markDirty("tags"); setTagsInput(e.target.value); }}
              className="w-full px-3 py-2 bg-surface-2 border border-border rounded text-sm text-gray-200 focus:outline-none focus:border-primary"
            />
          </div>

          <div className="pt-2 flex justify-end gap-3">
            <button
              data-testid="profile-edit-submit"
              type="submit"
              disabled={updateMutation.isPending || !name.trim()}
              className="px-4 py-2 bg-primary text-primary-foreground font-medium rounded text-sm hover:opacity-90 disabled:opacity-50"
            >
              {updateMutation.isPending ? t("saving") : t("save")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
