import { useState } from "react";
import { Outlet, useNavigate, useSearchParams, Link } from "react-router-dom";
import {
  Plus,
  Settings as SettingsIcon,
  LogOut,
  Play,
  Square,
  Globe,
  PanelLeftClose,
  PanelLeft,
} from "lucide-react";
import {
  useProfilesQuery,
  useProfileQuery,
  useProfileRuntimeQuery,
  useSetDesiredStateMutation,
  useStopProfileMutation,
  useApplyDisplaySettingsMutation,
} from "../features/profiles/useProfilesQuery";
import { useAuth } from "../features/auth/useAuth";
import { useI18n } from "../i18n";
import { useApiClient } from "../shared/api/client_context";

export function AppLayout() {
  const { t, locale, setLocale } = useI18n();
  const { logout } = useAuth();
  const client = useApiClient();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const currentProfileId = searchParams.get("profileId");

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [searchFilter, setSearchFilter] = useState("");

  const { data: profiles = [], isLoading: isProfilesLoading } = useProfilesQuery(client);
  const { data: activeProfile } = useProfileQuery(currentProfileId, client);
  const { data: activeRuntime } = useProfileRuntimeQuery(currentProfileId, client);

  const setDesiredStateMutation = useSetDesiredStateMutation(client);
  const stopProfileMutation = useStopProfileMutation(client);
  const applyDisplayMutation = useApplyDisplaySettingsMutation(client);

  const handleSelectProfile = (id: string) => {
    // Always land on this page instance's session route (AC-001).
    navigate({ pathname: "/", search: `?profileId=${encodeURIComponent(id)}` });
  };

  const handleLaunch = () => {
    if (!currentProfileId) return;
    setDesiredStateMutation.mutate({ id: currentProfileId, state: "running" });
  };

  const handleStop = () => {
    if (!currentProfileId) return;
    stopProfileMutation.mutate(currentProfileId);
  };

  const handleLogout = async () => {
    try {
      await logout();
    } catch {
      // Auth state is cleared locally; the route guard performs the redirect.
    }
    navigate("/login");
  };

  const filteredProfiles = profiles.filter((p) => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return (
      p.name.toLowerCase().includes(q) ||
      p.tags?.some((tag) => (typeof tag === "string" ? tag : tag.tag).toLowerCase().includes(q))
    );
  });

  const isRunning = activeRuntime?.observed_state === "running";
  const displayPending = Boolean(
    activeProfile &&
      isRunning &&
      activeRuntime &&
      activeRuntime.config_version !== activeProfile.current_config_version,
  );

  return (
    <div className="h-screen flex flex-col bg-surface-0 text-gray-100 overflow-hidden">
      {/* Top Navbar */}
      <header className="h-12 border-b border-border bg-surface-1 flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="text-gray-400 hover:text-gray-200 p-1"
            title={sidebarOpen ? t("hideSidebar") : t("showSidebar")}
          >
            {sidebarOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeft className="h-4 w-4" />}
          </button>

          <Link to="/" className="flex items-center gap-2 text-sm font-bold text-gray-100">
            <img src="/menubar-icon.svg" alt="CBrowser" className="h-5 w-5" />
            <span>CBrowser</span>
          </Link>

          {activeProfile && (
            <div
              data-testid="active-profile-header"
              className="ml-4 pl-4 border-l border-border flex items-center gap-2"
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  isRunning
                    ? "bg-emerald-400"
                    : activeRuntime?.observed_state === "starting"
                      ? "bg-amber-400 animate-pulse"
                      : "bg-gray-500"
                }`}
              />
              <span className="text-xs font-medium text-gray-200">{activeProfile.name}</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {activeProfile && (
            <>
              {displayPending && (
                <div
                  data-testid="display-pending-badge"
                  className="flex items-center gap-2 pl-2 pr-1 py-0.5 rounded bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[11px]"
                >
                  <span>{t("displaySettingsSavedPending")}</span>
                  <button
                    type="button"
                    data-testid="display-apply-restart-btn"
                    onClick={() => applyDisplayMutation.mutate(activeProfile.id)}
                    disabled={applyDisplayMutation.isPending}
                    className="px-2 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 disabled:opacity-50"
                  >
                    {applyDisplayMutation.isPending
                      ? t("displayApplyingRestart")
                      : t("displayApplyAndRestart")}
                  </button>
                </div>
              )}
              {isRunning ? (
                <button
                  type="button"
                  data-testid="header-stop-btn"
                  onClick={handleStop}
                  disabled={stopProfileMutation.isPending}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/30 transition-colors"
                >
                  <Square className="h-3 w-3 fill-current" />
                  {t("stop")}
                </button>
              ) : (
                <button
                  type="button"
                  data-testid="header-launch-btn"
                  onClick={handleLaunch}
                  disabled={
                    setDesiredStateMutation.isPending ||
                    activeRuntime?.observed_state === "starting"
                  }
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 border border-emerald-500/30 transition-colors"
                >
                  <Play className="h-3 w-3 fill-current" />
                  {t("launch")}
                </button>
              )}
            </>
          )}

          {/* Language Toggle */}
          <button
            type="button"
            onClick={() => setLocale(locale === "en" ? "zh" : "en")}
            className="p-1.5 text-gray-400 hover:text-gray-200 rounded text-xs flex items-center gap-1"
            title={t("switchLanguage")}
          >
            <Globe className="h-3.5 w-3.5" />
            <span className="text-[11px] uppercase font-mono">{locale}</span>
          </button>

          {/* Settings Link */}
          <Link
            to="/settings"
            className="p-1.5 text-gray-400 hover:text-gray-200 rounded"
            title={t("settings")}
          >
            <SettingsIcon className="h-4 w-4" />
          </Link>

          {/* Logout */}
          <button
            type="button"
            onClick={handleLogout}
            className="p-1.5 text-gray-400 hover:text-red-400 rounded"
            title={t("logOut")}
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </header>

      {applyDisplayMutation.error && (
        <div
          data-testid="display-apply-error"
          role="alert"
          className="px-4 py-1.5 bg-red-500/10 border-b border-red-500/30 text-red-300 text-xs"
        >
          {t("displayApplyFailed", { error: applyDisplayMutation.error.message })}
        </div>
      )}

      {activeRuntime?.last_coordinator_error && (
        <div
          data-testid="runtime-coordinator-error"
          role="alert"
          className="px-4 py-1.5 bg-amber-500/10 border-b border-amber-500/30 text-amber-300 text-xs"
        >
          {t("runtimeCoordinatorError", { error: activeRuntime.last_coordinator_error })}
        </div>
      )}

      {/* Main Body */}
      <div className="flex-1 flex min-h-0">
        {/* Sidebar */}
        {sidebarOpen && (
          <aside className="w-64 border-r border-border bg-surface-1 flex flex-col shrink-0">
            <div className="p-3 border-b border-border flex items-center justify-between gap-2">
              <input
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder={t("searchProfiles")}
                className="flex-1 px-2.5 py-1 bg-surface-2 border border-border rounded text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-primary"
              />
              <Link
                to="/profiles/new"
                data-testid="new-profile-link"
                className="p-1.5 bg-primary text-primary-foreground rounded hover:opacity-90 transition-opacity shrink-0"
                title={t("newProfile")}
              >
                <Plus className="h-3.5 w-3.5" />
              </Link>
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {isProfilesLoading ? (
                <div className="p-4 text-center text-xs text-gray-500">{t("loading")}</div>
              ) : filteredProfiles.length === 0 ? (
                <div className="p-4 text-center text-xs text-gray-500">
                  {searchFilter ? t("noMatches") : t("noProfilesYet")}
                </div>
              ) : (
                filteredProfiles.map((p) => {
                  const isSelected = p.id === currentProfileId;
                  return (
                    <button
                      key={p.id}
                      type="button"
                      data-testid={`profile-item-${p.id}`}
                      onClick={() => handleSelectProfile(p.id)}
                      className={`w-full text-left px-3 py-2 rounded text-xs flex items-center justify-between transition-colors ${
                        isSelected
                          ? "bg-primary/15 text-primary border border-primary/30"
                          : "text-gray-300 hover:bg-surface-2 hover:text-gray-100"
                      }`}
                    >
                      <div className="truncate flex-1 mr-2">
                        <div className="font-medium truncate">{p.name}</div>
                        {p.tags && p.tags.length > 0 && (
                          <div className="text-[10px] text-gray-500 truncate mt-0.5">
                            {p.tags.map((tag) => typeof tag === "string" ? `#${tag}` : `#${tag.tag}`).join(" ")}
                          </div>
                        )}
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </aside>
        )}

        {/* Content Outlet */}
        <main className="flex-1 flex flex-col min-w-0 min-h-0 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
