import { useQueries } from "@tanstack/react-query";
import { useApiClient } from "../../shared/api/client_context";
import type { ProfileResponse } from "../../shared/api/types";
import { Popover } from "../../shared/ui";
import { useI18n } from "../../i18n";
import { profileKeys } from "../profiles/useProfilesQuery";

export function ProxyUsedByPopover({
  profiles,
  open,
  onOpenChange,
  onOpenProfile,
}: {
  profiles: ProfileResponse[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onOpenProfile: (profile: ProfileResponse) => void;
}) {
  const { t } = useI18n();
  const client = useApiClient();
  const runtimeQueries = useQueries({
    queries: profiles.map((profile) => ({
      queryKey: profileKeys.runtime(profile.id),
      queryFn: () => client.profiles.getRuntime(profile.id),
      enabled: open,
    })),
  });

  return (
    <Popover
      trigger={<span />}
      open={open}
      onOpenChange={onOpenChange}
      ariaLabel={t("proxyColUsedBy")}
      contentClassName="w-(--container-dropdown-list)"
    >
      <div data-testid="proxy-used-by-popover" className="flex flex-col gap-xs">
        <p className="font-ui text-label-md text-on-surface-muted">
          {t("proxyUsedByCount", { count: profiles.length })}
        </p>
        <ul className="flex flex-col gap-2xs">
          {profiles.map((profile, index) => {
            const state = runtimeQueries[index]?.data?.observed_state;
            const running = state === "running";
            return (
              <li key={profile.id}>
                <button
                  type="button"
                  data-testid={`proxy-used-by-item-${profile.id}`}
                  onClick={() => {
                    onOpenChange(false);
                    onOpenProfile(profile);
                  }}
                  className="flex w-full items-center gap-sm rounded-sm px-sm py-xs font-ui text-body-md text-on-surface hover:bg-surface-hover"
                >
                  <span
                    aria-hidden="true"
                    className={`size-(--component-group-chip-size) shrink-0 rounded-full ${
                      running ? "bg-success" : "bg-on-surface-muted"
                    }`}
                  />
                  <span className="truncate">{profile.name}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </Popover>
  );
}
