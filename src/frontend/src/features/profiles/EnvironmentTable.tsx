import {
  AlertCircle,
  AppWindow,
  Copy,
  ExternalLink,
  Laptop,
  Monitor,
  Pencil,
  Play,
  SlidersHorizontal,
  Square,
  Trash2,
} from "lucide-react";
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
  IconButton,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
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
  | "details"
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
  return <Icon aria-hidden="true" className="size-(--component-icon-md-size) text-on-surface-muted" />;
}

export function formatPlatformLabel(
  platform: string | null | undefined,
  t: (key: TranslationKey) => string,
): string {
  return platform === "macos"
    ? t("formPlatformMacos")
    : t("formPlatformWindows");
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
  const running = observed === "running";
  const starting = observed === "starting";
  const stopping = observed === "stopping";
  const transitional = starting || stopping;
  const canStop = running || starting;
  const id = row.profile.id;
  const iconClass = "size-(--component-icon-sm-size)";

  return (
    <div className="flex flex-wrap items-center gap-xs">
      {running ? (
        <Button
          size="sm"
          variant="primary"
          data-testid={`env-action-open-${id}`}
          onClick={() => onAction("open", row)}
        >
          <ExternalLink aria-hidden="true" className={iconClass} />
          {t("envOpen")}
        </Button>
      ) : (
        <Button
          size="sm"
          variant="secondary"
          disabled={transitional}
          data-testid={`env-action-start-${id}`}
          onClick={() => onAction("start", row)}
        >
          <Play aria-hidden="true" className={iconClass} />
          {t("envStart")}
        </Button>
      )}

      <IconButton
        label={t("envDetails")}
        title={t("envDetails")}
        data-testid={`env-action-details-${id}`}
        onClick={() => onAction("details", row)}
      >
        <SlidersHorizontal aria-hidden="true" className={iconClass} />
      </IconButton>
      <IconButton
        label={t("envEdit")}
        title={t("envEdit")}
        data-testid={`env-action-edit-${id}`}
        onClick={() => onAction("edit", row)}
      >
        <Pencil aria-hidden="true" className={iconClass} />
      </IconButton>
      <IconButton
        label={t("envDuplicate")}
        title={t("envDuplicate")}
        data-testid={`env-action-copy-${id}`}
        onClick={() => onAction("duplicate", row)}
      >
        <Copy aria-hidden="true" className={iconClass} />
      </IconButton>
      {canStop ? (
        <IconButton
          variant="warning"
          label={t("envStop")}
          title={t("envStop")}
          disabled={stopping}
          data-testid={`env-action-stop-${id}`}
          onClick={() => onAction("stop", row)}
        >
          <Square aria-hidden="true" className={iconClass} />
        </IconButton>
      ) : (
        <IconButton
          variant="danger"
          label={t("envDelete")}
          title={t("envDelete")}
          disabled={stopping}
          data-testid={`env-action-delete-${id}`}
          onClick={() => onAction("delete", row)}
        >
          <Trash2 aria-hidden="true" className={iconClass} />
        </IconButton>
      )}
    </div>
  );
}

export function DirectNetwork({ id }: { id: string }) {
  const { t } = useI18n();
  return (
    <span
      data-testid={`env-direct-${id}`}
      className="font-ui text-body-sm text-on-surface-muted"
    >
      {t("envDirect")}
    </span>
  );
}

export function ProxyNetwork({ proxy }: { proxy: ProxyResponse }) {
  return (
    <span className="font-ui text-body-sm text-on-surface">
      {proxy.name}
    </span>
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
            <TableHead className="w-table-select">
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
            const platformLabel = formatPlatformLabel(
              row.profile.fingerprint_platform,
              t,
            );
            const tzLabel = row.profile.timezone || "";
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
                  <div className="flex items-center gap-xs">
                    <span className="font-ui text-body-md text-on-surface">
                      {row.profile.name}
                    </span>
                    {row.profile.notes && (
                      <Tooltip content={row.profile.notes}>
                        <span
                          data-testid={`env-note-trigger-${id}`}
                          aria-label={row.profile.notes}
                          className="inline-flex cursor-help items-center text-on-surface-muted hover:text-on-surface"
                        >
                          <AlertCircle
                            aria-hidden="true"
                            className="size-(--component-icon-sm-size)"
                          />
                        </span>
                      </Tooltip>
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
                      {platformLabel}
                    </span>
                    {tzLabel && (
                      <span className="font-ui text-label-sm text-on-surface-muted">
                        · {tzLabel}
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
