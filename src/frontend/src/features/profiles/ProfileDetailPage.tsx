import { useLocation, useParams } from "react-router";
import { Button, GroupChip, StatusBadge } from "../../shared/ui";
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
  const { data: profile } = useProfileQuery(profileId, client);
  const { data: runtime } = useProfileRuntimeQuery(profileId, client);
  const { data: groups } = useGroupsQuery(client);
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
        <a
          data-testid="profile-detail-open-session"
          href={`/session/${profileId}`}
          className="rounded-md border border-outline px-md py-sm font-ui text-label-md text-on-surface hover:bg-surface-hover"
        >
          {t("detailOpenSession")}
        </a>
        <Button
          data-testid="profile-detail-start"
          variant="primary"
          onClick={() =>
            startMutation.mutate({ id: profileId, state: "running" })
          }
        >
          {t("detailStart")}
        </Button>
        <Button
          data-testid="profile-detail-stop"
          variant="stop"
          onClick={() => stopMutation.mutate(profileId)}
        >
          {t("detailStop")}
        </Button>
      </header>

      <nav
        data-testid="profile-detail-tabs"
        className="flex gap-sm border-b border-outline"
      >
        {TABS.map((tab) => (
          <a
            key={tab.key}
            data-testid={`profile-tab-${tab.key}`}
            href={`/profiles/${profileId}/${tab.key}`}
            className="rounded-md px-md py-sm font-ui text-label-md text-on-surface hover:bg-surface-hover"
          >
            {t(tab.label)}
          </a>
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
