import { AppWindow, Laptop, Monitor } from "lucide-react";
import { useI18n, type TranslationKey } from "../../i18n";
import type {
  GroupResponse,
  ProfileResponse,
  ProfileRuntimeResponse,
  ProxyResponse,
} from "../../shared/api/types";
import {
  Button,
  Checkbox,
  GroupChip,
  ProtocolChip,
  RegionCode,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  WarningIcon,
  type StatusTone,
} from "../../shared/ui";
import { formatRelativeTime } from "./formatRelativeTime";

export interface EnvironmentRow {
  profile: ProfileResponse;
  runtime?: ProfileRuntimeResponse;
  group?: GroupResponse;
  proxy?: ProxyResponse;
}

export type EnvironmentAction =
  | "open"
  | "start"
  | "stop"
  | "edit"
  | "duplicate"
  | "delete";

interface StatusDescriptor {
  tone: StatusTone;
  label: TranslationKey;
}

const STATUS_MAP: Record<string, StatusDescriptor> = {
  starting: { tone: "transition", label: "statusStarting" },
  stopping: { tone: "transition", label: "statusStopping" },
  running: { tone: "running", label: "statusRunning" },
  error: { tone: "error", label: "statusError" },
  stopped: { tone: "stopped", label: "statusStopped" },
};

export function statusDescriptor(
  observed: string | undefined,
): StatusDescriptor {
  return STATUS_MAP[observed ?? "stopped"] ?? STATUS_MAP.stopped!;
}

export function PlatformIcon({
  platform,
}: {
  platform: string | null | undefined;
}) {
  const value = platform ?? "windows";
  const Icon =
    value === "macos" ? Laptop : value === "linux" ? Monitor : AppWindow;
  return <Icon aria-hidden="true" className="h-4 w-4 text-on-surface-muted" />;
}

export function EnvironmentRowActions({
  row,
  onAction,
}: {
  row: EnvironmentRow;
  onAction: (action: EnvironmentAction, row: EnvironmentRow) => void;
}) {
  const { t } = useI18n();
  const observed = row.runtime?.observed_state ?? "stopped";
  const running = observed === "running" || observed === "starting";
  const stopping = observed === "stopping";
  const actions: Array<{
    key: EnvironmentAction;
    label: string;
    disabled?: boolean;
  }> = [
    { key: "open", label: t("envOpen") },
    { key: "start", label: t("envStart"), disabled: running },
    { key: "stop", label: t("envStop"), disabled: stopping },
    { key: "edit", label: t("envEdit") },
    { key: "duplicate", label: t("envDuplicate") },
    { key: "delete", label: t("envDelete") },
  ];

  return (
    <div className="flex flex-wrap items-center gap-xs">
      {actions.map((action) => (
        <Button
          key={action.key}
          size="sm"
          variant={action.key === "delete" ? "danger" : "ghost"}
          disabled={action.disabled}
          data-testid={`env-action-${action.key}-${row.profile.id}`}
          onClick={() => onAction(action.key, row)}
        >
          {action.label}
        </Button>
      ))}
    </div>
  );
}

export function DirectNetwork({ id }: { id: string }) {
  const { t } = useI18n();
  return (
    <span
      data-testid={`env-direct-${id}`}
      className="inline-flex flex-wrap items-center gap-xs"
    >
      <WarningIcon className="text-warning" />
      <span className="font-ui text-body-sm text-warning">{t("envDirect")}</span>
      <span
        data-testid={`env-direct-warning-${id}`}
        className="font-ui text-label-sm text-on-surface-muted"
      >
        {t("envDirectWarning")}
      </span>
    </span>
  );
}

export function ProxyNetwork({ proxy }: { proxy: ProxyResponse }) {
  return (
    <div className="flex flex-wrap items-center gap-sm">
      <span className="font-ui text-body-sm text-on-surface">{proxy.name}</span>
      <ProtocolChip protocol={proxy.scheme} />
      {proxy.country_code && <RegionCode code={proxy.country_code} />}
    </div>
  );
}

export function EnvironmentTable({
  rows,
  selected,
  onToggle,
  onToggleAll,
  onAction,
}: {
  rows: EnvironmentRow[];
  selected: Set<string>;
  onToggle: (id: string, checked: boolean) => void;
  onToggleAll: (checked: boolean) => void;
  onAction: (action: EnvironmentAction, row: EnvironmentRow) => void;
}) {
  const { t } = useI18n();
  const allSelected =
    rows.length > 0 && rows.every((row) => selected.has(row.profile.id));

  return (
    <div
      data-testid="env-table"
      className="overflow-x-auto rounded-lg border border-outline"
    >
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">
              <span data-testid="env-select-all">
                <Checkbox
                  checked={allSelected}
                  onCheckedChange={onToggleAll}
                  label={t("envSelectAll")}
                />
              </span>
            </TableHead>
            <TableHead>{t("envColName")}</TableHead>
            <TableHead>{t("envColGroup")}</TableHead>
            <TableHead>{t("envColNetwork")}</TableHead>
            <TableHead>{t("envColFingerprint")}</TableHead>
            <TableHead>{t("envColStatus")}</TableHead>
            <TableHead>{t("envColLastActive")}</TableHead>
            <TableHead>{t("envColActions")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => {
            const id = row.profile.id;
            const observed = row.runtime?.observed_state ?? "stopped";
            const status = statusDescriptor(observed);
            const errorReason =
              row.runtime?.last_coordinator_error ?? row.profile.name;
            const running = observed === "running";
            return (
              <TableRow
                key={id}
                data-testid={`env-row-${id}`}
                selected={selected.has(id)}
              >
                <TableCell>
                  <span data-testid={`env-select-${id}`}>
                    <Checkbox
                      checked={selected.has(id)}
                      onCheckedChange={(checked) => onToggle(id, checked)}
                      label={row.profile.name}
                    />
                  </span>
                </TableCell>
                <TableCell>
                  <div className="flex flex-col gap-xs">
                    <span className="font-ui text-body-md text-on-surface">
                      {row.profile.name}
                    </span>
                    {row.profile.notes && (
                      <span className="font-ui text-label-sm text-on-surface-muted">
                        {row.profile.notes}
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  {row.group ? (
                    <GroupChip label={row.group.name} hue={row.group.color} />
                  ) : (
                    <span className="font-ui text-body-sm text-on-surface-muted">
                      {t("envUngrouped")}
                    </span>
                  )}
                </TableCell>
                <TableCell>
                  {row.proxy ? (
                    <ProxyNetwork proxy={row.proxy} />
                  ) : (
                    <DirectNetwork id={id} />
                  )}
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap items-center gap-sm">
                    <PlatformIcon platform={row.profile.fingerprint_platform} />
                    <span className="font-ui text-body-sm text-on-surface">
                      {row.profile.fingerprint_platform ?? "windows"}
                    </span>
                    {row.profile.geoip && (
                      <span className="font-ui text-label-sm text-on-surface-muted">
                        {t("envGeoipFollowProxy")}
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <div
                    data-testid={`env-status-${id}`}
                    className="flex flex-wrap items-center gap-sm"
                  >
                    {observed === "error" ? (
                      <Tooltip content={t("envErrorReason", { name: errorReason })}>
                        <span data-testid={`env-error-tooltip-${id}`}>
                          <StatusBadge
                            tone={status.tone}
                            label={t(status.label)}
                          />
                        </span>
                      </Tooltip>
                    ) : (
                      <StatusBadge tone={status.tone} label={t(status.label)} />
                    )}
                    {observed === "error" && (
                      <span
                        data-testid={`env-error-reason-${id}`}
                        className="font-ui text-label-sm text-on-surface-muted"
                      >
                        {t("envErrorReason", { name: errorReason })}
                      </span>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <span className="font-ui text-body-sm text-on-surface-muted">
                    {running
                      ? t("envRunningFor", {
                          time: formatRelativeTime(
                            row.runtime?.last_started_at,
                          ),
                        })
                      : t("envLastStopped", {
                          time: formatRelativeTime(
                            row.runtime?.last_stopped_at,
                          ),
                        })}
                  </span>
                </TableCell>
                <TableCell>
                  <EnvironmentRowActions row={row} onAction={onAction} />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
