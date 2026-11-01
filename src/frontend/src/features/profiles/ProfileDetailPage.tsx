import { useState, useEffect, type FormEvent } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { ArrowLeft, Trash2, FolderArchive, Cpu } from "lucide-react";
import {
  useProfileQuery,
  useProfileRuntimeQuery,
  useUpdateProfileMutation,
  useDeleteProfileMutation,
  useApplyDisplaySettingsMutation,
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

  const [name, setName] = useState("");
  const [proxy, setProxy] = useState("");
  const [screenWidth, setScreenWidth] = useState(1920);
  const [screenHeight, setScreenHeight] = useState(1080);
  const [tagsInput, setTagsInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (profile) {
      setName(profile.name || "");
      setProxy(profile.proxy || "");
      setScreenWidth(profile.screen_width || 1920);
      setScreenHeight(profile.screen_height || 1080);
      setTagsInput(
        profile.tags
          ? profile.tags.map((t) => (typeof t === "string" ? t : t.tag)).join(", ")
          : "",
      );
    }
  }, [profile]);

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
        </div>
      </div>

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
              onChange={(e) => setName(e.target.value)}
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
              onChange={(e) => setProxy(e.target.value)}
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
                onChange={(e) => setScreenWidth(Number(e.target.value))}
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
                onChange={(e) => setScreenHeight(Number(e.target.value))}
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
              onChange={(e) => setTagsInput(e.target.value)}
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
