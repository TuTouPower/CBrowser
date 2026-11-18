import { useMemo, useState } from "react";
import { Link } from "react-router";
import { ChevronDown } from "lucide-react";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import type {
  GroupResponse,
  ProfileResponse,
} from "../../shared/api/types";
import {
  Popover,
  SearchField,
  type StatusTone,
} from "../../shared/ui";
import { environmentStatusDescriptor } from "../../shared/presentation";
import {
  useProfileRuntimeQuery,
  useRuntimeSummaryQuery,
} from "../profiles/useProfilesQuery";
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

export function currentStatus(
  observed: string | undefined,
  t: ReturnType<typeof useI18n>["t"],
): { tone: StatusTone; label: string } {
  // t079 AC-002/AC-003: one shared status vocabulary; an unloaded or
  // unknown state reads "unknown", never a disguised "stopped".
  const descriptor = environmentStatusDescriptor(observed);
  return { tone: descriptor.tone, label: t(descriptor.label) };
}

export function statusDotClass(tone: StatusTone): string {
  switch (tone) {
    case "running":
      return "size-(--component-group-chip-size) shrink-0 rounded-full bg-success";
    case "transition":
      return "size-(--component-group-chip-size) shrink-0 rounded-full bg-warning";
    case "error":
      return "size-(--component-group-chip-size) shrink-0 rounded-full bg-danger";
    default:
      return "size-(--component-group-chip-size) shrink-0 rounded-full bg-on-surface-muted";
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
  const [open, setOpen] = useState(false);

  const current = profiles.find((profile) => profile.id === currentProfileId);
  // t076 AC-002 (p121): a closed switcher issues no per-profile runtime
  // requests. The trigger only needs the current profile (one read);
  // the item list reads one batched summary, and only while open.
  const { data: currentRuntime } = useProfileRuntimeQuery(
    currentProfileId,
    client,
  );
  const { data: summary } = useRuntimeSummaryQuery(client, { enabled: open });
  const observedById = new Map<string, string | undefined>();
  for (const entry of summary?.entries ?? []) {
    observedById.set(entry.profile_id, entry.observed_state);
  }
  if (currentRuntime) {
    observedById.set(currentProfileId, currentRuntime.observed_state);
  }

  const currentItemStatus = currentStatus(
    observedById.get(currentProfileId),
    t,
  );

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
      open={open}
      onOpenChange={setOpen}
      trigger={
        <button
          type="button"
          data-testid={SESS_SWITCHER_TRIGGER}
          aria-label={t("sessSwitcher")}
          className="inline-flex h-(--component-select-height) items-center gap-sm rounded-md border border-outline bg-surface px-md font-ui text-label-md text-on-surface hover:bg-surface-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          <span
            data-testid="sess-switcher-trigger-dot"
            aria-hidden="true"
            className={statusDotClass(currentItemStatus.tone)}
          />
          <span className="truncate">{current?.name ?? currentProfileId}</span>
          <ChevronDown
            aria-hidden="true"
            className="size-(--component-icon-sm-size) shrink-0 text-on-surface-muted"
          />
        </button>
      }
    >
      <div
        data-testid={SESS_SWITCHER_POPOVER}
        className="flex flex-1 flex-col gap-sm overflow-hidden"
      >
        <SearchField
          data-testid={SESS_SWITCHER_SEARCH}
          label={t("sessSwitcherSearch")}
          placeholder={t("sessSwitcherSearch")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        {/* t077 AC-004: the list scrolls inside the popover instead
            of a fixed panel height that can run past the viewport. */}
        {sections.length === 0 ? (
          <p className="px-sm py-md font-ui text-body-sm text-on-surface-muted">
            {t("sessSwitcherEmpty")}
          </p>
        ) : (
          <div className="flex flex-1 flex-col gap-sm overflow-y-auto">
            {sections.map((section) => (
              <div key={section.key} className="flex flex-col gap-xs">
                <p
                  data-testid={SESS_SWITCHER_GROUP}
                  className="px-sm font-ui text-label-sm text-on-surface-muted"
                >
                  {section.label}
                </p>
                <ul className="flex flex-col gap-xs">
                  {section.items.map((profile) => {
                    const itemStatus = currentStatus(
                      observedById.get(profile.id),
                      t,
                    );
                    return (
                      <li
                        key={profile.id}
                        data-testid={SESS_SWITCHER_ITEM}
                      >
                        <Link
                          data-testid={sessId("switcher-item", profile.id)}
                          to={`/session/${encodeURIComponent(profile.id)}`}
                          onClick={() => setOpen(false)}
                          aria-label={`${profile.name} (${itemStatus.label})`}
                          className="flex items-center gap-sm rounded-sm px-sm py-xs font-ui text-body-md text-on-surface hover:bg-surface-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                        >
                          <span className="flex min-w-none items-center gap-sm truncate">
                            <span
                              data-testid={sessId("switcher-dot", profile.id)}
                              aria-hidden="true"
                              className={statusDotClass(itemStatus.tone)}
                            />
                            <span className="truncate">{profile.name}</span>
                            {/* t079 AC-003: no duplicate right-side badge;
                                the status stays available to assistive
                                tech as text, not color alone. */}
                            <span className="sr-only">{itemStatus.label}</span>
                          </span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
    </Popover>
  );
}
