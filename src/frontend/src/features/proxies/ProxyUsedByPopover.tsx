import { useApiClient } from "../../shared/api/client_context";
import type { ProxyUsedByEntry } from "../../shared/api/types";
import { Popover } from "../../shared/ui";
import { useI18n } from "../../i18n";
import { useRuntimeSummaryQuery } from "../profiles/useProfilesQuery";

function kindLabel(
  kind: ProxyUsedByEntry["kind"],
  t: ReturnType<typeof useI18n>["t"],
): string {
  switch (kind) {
    case "current":
      return t("proxyUsedByKindCurrent");
    case "bound":
      return t("proxyUsedByKindBound");
    case "both":
      return t("proxyUsedByKindBoth");
  }
}

export function ProxyUsedByPopover({
  entries,
  open,
  onOpenChange,
  onOpenProfile,
}: {
  /** Union detail from GET /proxies/{id}/used-by — same口径 as the count. */
  entries: ProxyUsedByEntry[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onOpenProfile: (profile: { id: string }) => void;
}) {
  const { t } = useI18n();
  const client = useApiClient();
  // t076 AC-002/AC-004 (p121): running dots come from one batched
  // summary, read only while the popover is open.
  const { data: summary } = useRuntimeSummaryQuery(client, { enabled: open });
  const observedById = new Map(
    (summary?.entries ?? []).map((entry) => [
      entry.profile_id,
      entry.observed_state,
    ]),
  );

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
          {t("proxyUsedByCount", { count: entries.length })}
        </p>
        <ul className="flex flex-col gap-2xs">
          {entries.map((entry) => {
            const running = observedById.get(entry.profile_id) === "running";
            return (
              <li key={entry.profile_id}>
                <button
                  type="button"
                  data-testid={`proxy-used-by-item-${entry.profile_id}`}
                  onClick={() => {
                    onOpenChange(false);
                    onOpenProfile({ id: entry.profile_id });
                  }}
                  className="flex w-full items-center gap-sm rounded-sm px-sm py-xs font-ui text-body-md text-on-surface hover:bg-surface-hover"
                >
                  <span
                    aria-hidden="true"
                    className={`size-(--component-group-chip-size) shrink-0 rounded-full ${
                      running ? "bg-success" : "bg-on-surface-muted"
                    }`}
                  />
                  <span className="truncate">{entry.name}</span>
                  <span
                    data-testid={`proxy-used-by-kind-${entry.profile_id}`}
                    className="ml-auto shrink-0 font-ui text-body-sm text-on-surface-muted"
                  >
                    {kindLabel(entry.kind, t)}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </Popover>
  );
}
