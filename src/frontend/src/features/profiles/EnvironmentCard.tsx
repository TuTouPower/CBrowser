import { useI18n } from "../../i18n";
import { Checkbox, GroupChip, StatusBadge } from "../../shared/ui";
import { formatRelativeTime } from "./formatRelativeTime";
import {
  DirectNetwork,
  EnvironmentRowActions,
  PlatformIcon,
  ProxyNetwork,
  statusDescriptor,
  type EnvironmentAction,
  type EnvironmentRow,
} from "./EnvironmentTable";

export function EnvironmentCard({
  row,
  selected,
  onToggle,
  onAction,
}: {
  row: EnvironmentRow;
  selected: boolean;
  onToggle: (id: string, checked: boolean) => void;
  onAction: (action: EnvironmentAction, row: EnvironmentRow) => void;
}) {
  const { t } = useI18n();
  const id = row.profile.id;
  const observed = row.runtime?.observed_state ?? "stopped";
  const status = statusDescriptor(observed);
  const running = observed === "running";

  return (
    <div
      data-testid={`env-card-${id}`}
      className="flex flex-col gap-sm rounded-lg border border-outline bg-surface p-md"
    >
      <div
        data-testid={`env-card-preview-${id}`}
        className="aspect-video w-full rounded-md bg-surface-subtle"
      />
      <div className="flex flex-wrap items-center justify-between gap-sm">
        <span className="font-ui text-body-md text-on-surface">
          {row.profile.name}
        </span>
        <span data-testid={`env-select-${id}`}>
          <Checkbox
            checked={selected}
            onCheckedChange={(checked) => onToggle(id, checked)}
            label={row.profile.name}
          />
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-sm">
        <StatusBadge tone={status.tone} label={t(status.label)} />
        {row.group ? (
          <GroupChip label={row.group.name} hue={row.group.color} />
        ) : (
          <span className="font-ui text-label-sm text-on-surface-muted">
            {t("envUngrouped")}
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-sm">
        {row.proxy ? (
          <ProxyNetwork proxy={row.proxy} />
        ) : (
          <DirectNetwork id={id} />
        )}
      </div>
      <div className="flex flex-wrap items-center gap-sm">
        <PlatformIcon platform={row.profile.fingerprint_platform} />
        <span className="font-ui text-label-sm text-on-surface-muted">
          {row.profile.fingerprint_platform ?? "windows"}
        </span>
        {row.profile.geoip && (
          <span className="font-ui text-label-sm text-on-surface-muted">
            {t("envGeoipFollowProxy")}
          </span>
        )}
      </div>
      <span className="font-ui text-label-sm text-on-surface-muted">
        {running
          ? t("envRunningFor", {
              time: formatRelativeTime(row.runtime?.last_started_at),
            })
          : t("envLastStopped", {
              time: formatRelativeTime(row.runtime?.last_stopped_at),
            })}
      </span>
      <EnvironmentRowActions row={row} onAction={onAction} />
    </div>
  );
}
