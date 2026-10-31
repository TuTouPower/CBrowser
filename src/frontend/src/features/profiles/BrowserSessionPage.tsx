import { useSearchParams, useNavigate, Link } from "react-router-dom";
import { Play, Settings as SettingsIcon, FolderArchive, Cpu, Compass } from "lucide-react";
import {
  useProfileQuery,
  useProfileRuntimeQuery,
  useSetDesiredStateMutation,
} from "./useProfilesQuery";
import { BrowserSessionMount } from "../../shared/components/BrowserSessionMount";
import { useI18n } from "../../i18n";

export function BrowserSessionPage() {
  const [searchParams] = useSearchParams();
  const profileId = searchParams.get("profileId");
  const navigate = useNavigate();
  const { t } = useI18n();

  const { data: profile, isLoading: isProfileLoading } = useProfileQuery(profileId);
  const { data: runtime, isLoading: isRuntimeLoading } = useProfileRuntimeQuery(profileId);
  const setDesiredStateMutation = useSetDesiredStateMutation();

  if (!profileId) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-surface-0">
        <Compass className="h-12 w-12 text-gray-600 mb-3" />
        <h2 className="text-base font-semibold text-gray-200 mb-1">
          {t("selectOrCreateProfile")}
        </h2>
        <p className="text-xs text-gray-500 max-w-sm mb-4">
          {t("sessionSelectHint")}
        </p>
        <Link
          to="/profiles/new"
          className="px-4 py-2 bg-primary text-primary-foreground text-xs font-medium rounded hover:opacity-90 transition-opacity"
        >
          + {t("newProfile")}
        </Link>
      </div>
    );
  }

  if (isProfileLoading || isRuntimeLoading) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
        {t("loading")}
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">
        {t("profileNotFound")}
      </div>
    );
  }

  const isRunning = runtime?.observed_state === "running";

  if (isRunning) {
    return (
      <BrowserSessionMount
        profileId={profileId}
        onCheckRuntimeStatus={() => navigate(`/profiles/${profileId}`)}
      />
    );
  }

  const handleLaunch = () => {
    setDesiredStateMutation.mutate({ id: profileId, state: "running" });
  };

  return (
    <div className="flex-1 flex items-center justify-center p-6 bg-surface-0">
      <div
        data-testid="session-runtime-not-ready"
        className="max-w-md w-full bg-surface-1 border border-border rounded-xl p-8 text-center shadow-lg"
      >
        <div className="h-16 w-16 mx-auto mb-4 rounded-full bg-surface-2 flex items-center justify-center border border-border">
          <span className="text-2xl font-bold text-gray-300">
            {profile.name.charAt(0).toUpperCase()}
          </span>
        </div>

        <h2
          data-testid="session-runtime-not-ready-title"
          className="text-lg font-bold text-gray-100 mb-1"
        >
          {t("runtimeNotReady")}
        </h2>
        <p className="text-xs text-gray-500 mb-2">{profile.name}</p>
        <div className="flex items-center justify-center gap-2 mb-4">
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              runtime?.observed_state === "starting" ? "bg-amber-400 animate-pulse" : "bg-gray-500"
            }`}
          />
          <span className="text-xs text-gray-400 capitalize">
            {runtime?.observed_state || "stopped"}
          </span>
        </div>

        {profile.tags && profile.tags.length > 0 && (
          <div className="flex flex-wrap justify-center gap-1.5 mb-6">
            {profile.tags.map((tag, idx) => {
              const tagStr = typeof tag === "string" ? tag : tag.tag;
              return (
                <span
                  key={idx}
                  className="px-2 py-0.5 rounded text-[11px] bg-surface-2 text-gray-400 border border-border"
                >
                  #{tagStr}
                </span>
              );
            })}
          </div>
        )}

        {runtime?.last_coordinator_error && (
          <div
            data-testid="runtime-coordinator-error"
            className="mb-4 p-2.5 bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs rounded text-left"
          >
            {t("runtimeCoordinatorError", { error: runtime.last_coordinator_error })}
          </div>
        )}

        <button
          type="button"
          data-testid="session-launch-btn"
          onClick={handleLaunch}
          disabled={setDesiredStateMutation.isPending || runtime?.observed_state === "starting"}
          className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-primary text-primary-foreground font-semibold rounded-lg text-sm hover:opacity-90 disabled:opacity-50 transition-opacity mb-4"
        >
          <Play className="h-4 w-4 fill-current" />
          {runtime?.observed_state === "starting"
            ? t("startingBrowser")
            : t("launchRemoteBrowser")}
        </button>

        <div className="flex items-center justify-center gap-3 pt-3 border-t border-border">
          <Link
            to={`/profiles/${profile.id}`}
            className="inline-flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200"
          >
            <SettingsIcon className="h-3.5 w-3.5" />
            {t("configure")}
          </Link>
          <span className="text-gray-600">•</span>
          <Link
            to={`/profiles/${profile.id}/files`}
            className="inline-flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200"
          >
            <FolderArchive className="h-3.5 w-3.5" />
            {t("files")}
          </Link>
          <span className="text-gray-600">•</span>
          <Link
            to={`/automation/${profile.id}`}
            className="inline-flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200"
          >
            <Cpu className="h-3.5 w-3.5" />
            {t("automation")}
          </Link>
        </div>
      </div>
    </div>
  );
}
