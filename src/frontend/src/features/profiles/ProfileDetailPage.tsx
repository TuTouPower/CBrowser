import { Link, useLocation, useParams } from "react-router";
import { Banner, Button, GroupChip, StatusBadge } from "../../shared/ui";
import { useI18n, type TranslationKey } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import {
  useGroupsQuery,
  useProfileQuery,
  useProfileRuntimeQuery,
  useSetDesiredStateMutation,
  useStopProfileMutation,
} from "./useProfilesQuery";
import { ConfigTab } from "./ConfigTab";
import { SharedProfileBanners } from "./SharedProfileBanners";
import { MaintenanceTab } from "./MaintenanceTab";
import { ProfileFilesTab } from "../artifacts/ProfileFilesTab";
import { ProfileAutomationTab } from "../automation/ProfileAutomationTab";
import { statusDescriptor } from "./EnvironmentTable";

type TabKey = "config" | "files" | "automation" | "maintenance";

const TABS: Array<{ key: TabKey; label: TranslationKey }> = [
  { key: "config", label: "detailTabConfig" },
  { key: "files", label: "detailTabFiles" },
  { key: "automation", label: "detailTabAutomation" },
  { key: "maintenance", label: "detailTabMaintenance" },
];

export function ProfileDetailPage() {
  const { profileId = "" } = useParams<{ profileId: string }>();
  const { pathname } = useLocation();
  const { t } = useI18n();
  const client = useApiClient();
  const profileQuery = useProfileQuery(profileId, client);
  const runtimeQuery = useProfileRuntimeQuery(profileId, client);
  const groupsQuery = useGroupsQuery(client);
  const profile = profileQuery.data;
  const runtime = runtimeQuery.data;
  const groups = groupsQuery.data;
  const startMutation = useSetDesiredStateMutation(client);
  const stopMutation = useStopProfileMutation(client);

  const activeTab: TabKey = pathname.endsWith("/files")
    ? "files"
    : pathname.endsWith("/automation")
      ? "automation"
      : pathname.endsWith("/maintenance")
        ? "maintenance"
        : "config";

  const observed = runtime?.observed_state ?? "stopped";
  const status = statusDescriptor(observed);
  const group = groups?.find((item) => item.id === profile?.group_id);
  // P2: runtime 失败不阻塞配置页；仅 profile 失败才整页错误，runtime
  // 失败降级为顶栏 Banner，配置/文件/自动化/维护仍可访问。
  const profileLoadError = profileQuery.isError
    ? (profileQuery.error?.message ?? t("runtimeStateUnknown"))
    : null;
  const runtimeLoadError = runtimeQuery.isError
    ? (runtimeQuery.error?.message ?? t("runtimeStateUnknown"))
    : null;
  const controlPending = startMutation.isPending || stopMutation.isPending;
  const controlError =
    startMutation.isError || stopMutation.isError
      ? ((startMutation.error ?? stopMutation.error)?.message ??
        t("runtimeStateUnknown"))
      : null;
  if (profileLoadError) {
    return (
      <div
        data-testid="profile-detail-view"
        className="flex flex-col gap-lg p-lg"
      >
        <Banner tone="danger" testId="profile-detail-error">
          <span>{profileLoadError}</span>
          <Button
            size="sm"
            data-testid="profile-detail-retry"
            onClick={() => {
              if (profileQuery.isError) void profileQuery.refetch();
              if (runtimeQuery.isError) void runtimeQuery.refetch();
              if (groupsQuery.isError) void groupsQuery.refetch();
            }}
          >
            {t("retryAction")}
          </Button>
        </Banner>
      </div>
    );
  }

  return (
    <div
      data-testid="profile-detail-view"
      className="flex flex-col gap-lg p-lg"
    >
      <header className="flex flex-wrap items-center gap-md">
        <h1 className="font-ui text-headline-md text-on-surface">
          {profile?.name ?? ""}
        </h1>
        <div data-testid="profile-detail-status">
          <StatusBadge tone={status.tone} label={t(status.label)} />
        </div>
        {group && (
          <div data-testid="profile-detail-group">
            <GroupChip label={group.name} hue={group.color} />
          </div>
        )}
        <Link
          data-testid="profile-detail-open-session"
          to={`/session/${profileId}`}
          className="rounded-md border border-outline px-md py-sm font-ui text-label-md text-on-surface hover:bg-surface-hover"
        >
          {t("detailOpenSession")}
        </Link>
        <Button
          data-testid="profile-detail-start"
          variant="primary"
          disabled={controlPending}
          onClick={() =>
            startMutation.mutate({ id: profileId, state: "running" })
          }
        >
          {t("detailStart")}
        </Button>
        <Button
          data-testid="profile-detail-stop"
          variant="stop"
          disabled={controlPending}
          onClick={() => stopMutation.mutate(profileId)}
        >
          {t("detailStop")}
        </Button>
      </header>
      {controlError && (
        <Banner tone="danger" testId="profile-detail-control-error">
          {controlError}
        </Banner>
      )}
      {runtimeLoadError && (
        <Banner tone="danger" testId="profile-detail-runtime-error">
          <span>{runtimeLoadError}</span>
          <Button
            size="sm"
            data-testid="profile-detail-runtime-retry"
            onClick={() => void runtimeQuery.refetch()}
          >
            {t("retryAction")}
          </Button>
        </Banner>
      )}

      <nav
        data-testid="profile-detail-tabs"
        className="flex gap-sm border-b border-outline"
      >
        {TABS.map((tab) => (
          <Link
            key={tab.key}
            data-testid={`profile-tab-${tab.key}`}
            to={`/profiles/${profileId}/${tab.key}`}
            className="rounded-md px-md py-sm font-ui text-label-md text-on-surface hover:bg-surface-hover"
          >
            {t(tab.label)}
          </Link>
        ))}
      </nav>

      {activeTab === "config" ? (
        <ConfigTab profileId={profileId} />
      ) : (
        <>
          <SharedProfileBanners profileId={profileId} />
          {activeTab === "files" ? (
            <ProfileFilesTab profileId={profileId} />
          ) : activeTab === "automation" ? (
            <ProfileAutomationTab profileId={profileId} />
          ) : (
            <MaintenanceTab profileId={profileId} />
          )}
        </>
      )}
    </div>
  );
}
