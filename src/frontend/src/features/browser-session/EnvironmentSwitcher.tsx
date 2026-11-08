import { useMemo, useState } from "react";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import type { GroupResponse, ProfileResponse } from "../../shared/api/types";
import {
  Popover,
  SearchField,
  StatusBadge,
  type StatusTone,
} from "../../shared/ui";
import { useProfileRuntimeQuery } from "../profiles/useProfilesQuery";
import {
  SESS_SWITCHER_GROUP,
  SESS_SWITCHER_ITEM,
  SESS_SWITCHER_POPOVER,
  SESS_SWITCHER_SEARCH,
  SESS_SWITCHER_TRIGGER,
  sessId,
} from "./session_keys";

export interface EnvironmentSwitcherProps {
  currentProfileId: string;
  profiles: ProfileResponse[];
  groups: GroupResponse[];
}

interface SwitcherSection {
  key: string;
  label: string;
  items: ProfileResponse[];
}

function currentStatus(
  observed: string | undefined,
  t: ReturnType<typeof useI18n>["t"],
): { tone: StatusTone; label: string } {
  switch (observed) {
    case "running":
      return { tone: "running", label: t("sessRunning") };
    case "starting":
      return { tone: "transition", label: t("statusStarting") };
    case "stopping":
      return { tone: "transition", label: t("statusStopping") };
    case "error":
      return { tone: "error", label: t("statusError") };
    default:
      return { tone: "stopped", label: t("sessStopped") };
  }
}

export function EnvironmentSwitcher({
  currentProfileId,
  profiles,
  groups,
}: EnvironmentSwitcherProps) {
  const { t } = useI18n();
  const client = useApiClient();
  const [query, setQuery] = useState("");

  const current = profiles.find((profile) => profile.id === currentProfileId);
  const { data: runtime } = useProfileRuntimeQuery(currentProfileId, client);
  const status = currentStatus(runtime?.observed_state, t);

  const sections = useMemo<SwitcherSection[]>(() => {
    const normalized = query.trim().toLowerCase();
    const matching = profiles.filter((profile) =>
      profile.name.toLowerCase().includes(normalized),
    );
    const result: SwitcherSection[] = [];
    for (const group of groups) {
      const items = matching.filter(
        (profile) => profile.group_id === group.id,
      );
      if (items.length > 0) {
        result.push({ key: group.id, label: group.name, items });
      }
    }
    const ungrouped = matching.filter(
      (profile) =>
        !profile.group_id ||
        !groups.some((group) => group.id === profile.group_id),
    );
    if (ungrouped.length > 0) {
      result.push({
        key: "__ungrouped__",
        label: t("sessUngrouped"),
        items: ungrouped,
      });
    }
    return result;
  }, [query, profiles, groups, t]);

  return (
    <Popover
      ariaLabel={t("sessSwitcher")}
      trigger={
        <button
          type="button"
          data-testid={SESS_SWITCHER_TRIGGER}
          aria-label={t("sessSwitcher")}
          className="inline-flex h-9 items-center gap-sm rounded-md border border-outline bg-surface px-md font-ui text-label-md text-on-surface hover:bg-surface-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          <span className="truncate">{current?.name ?? currentProfileId}</span>
          <StatusBadge tone={status.tone} label={status.label} />
        </button>
      }
    >
      <div
        data-testid={SESS_SWITCHER_POPOVER}
        className="flex flex-col gap-sm"
      >
        <SearchField
          data-testid={SESS_SWITCHER_SEARCH}
          label={t("sessSwitcherSearch")}
          placeholder={t("sessSwitcherSearch")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        {sections.length === 0 ? (
          <p className="px-sm py-md font-ui text-body-sm text-on-surface-muted">
            {t("sessSwitcherEmpty")}
          </p>
        ) : (
          <div className="flex max-h-panel flex-col gap-sm overflow-y-auto">
            {sections.map((section) => (
              <div key={section.key} className="flex flex-col gap-xs">
                <p
                  data-testid={SESS_SWITCHER_GROUP}
                  className="px-sm font-ui text-label-sm text-on-surface-muted"
                >
                  {section.label}
                </p>
                <ul className="flex flex-col gap-xs">
                  {section.items.map((profile) => (
                    <li
                      key={profile.id}
                      data-testid={SESS_SWITCHER_ITEM}
                    >
                      <a
                        data-testid={sessId("switcher-item", profile.id)}
                        href={`/session/${encodeURIComponent(profile.id)}`}
                        className="block rounded-sm px-sm py-xs font-ui text-body-md text-on-surface hover:bg-surface-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                      >
                        {profile.name}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
    </Popover>
  );
}
