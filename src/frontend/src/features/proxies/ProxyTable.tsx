import {
  AlertCircle,
  Pencil,
  Trash2,
  Zap,
} from "lucide-react";
import { useI18n } from "../../i18n";
import type { ProxyResponse } from "../../shared/api/types";
import {
  IconButton,
  MonoValue,
  ProtocolChip,
  RegionCode,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
} from "../../shared/ui";

export interface ProxyTableProps {
  proxies: ProxyResponse[];
  onEdit: (proxy: ProxyResponse) => void;
  onDelete: (proxy: ProxyResponse) => void;
  onProbe: (proxy: ProxyResponse) => void;
  probingId?: string | null;
  /** t076 AC-004: the count comes from the backend union; the click
   * resolves the detail (single -> navigate, many -> popover) in the
   * page, so the table never derives used-by from current config. */
  onUsedByClick: (proxy: ProxyResponse) => void;
}

function usedByLabel(
  count: number,
  t: ReturnType<typeof useI18n>["t"],
): string {
  return count === 1
    ? t("proxyUsedByCountOne")
    : t("proxyUsedByCount", { count });
}

export function ProxyTable({
  proxies,
  onEdit,
  onDelete,
  onProbe,
  probingId,
  onUsedByClick,
}: ProxyTableProps) {
  const { t } = useI18n();

  return (
    <div
      data-testid="proxy-table"
      className="overflow-x-auto rounded-lg border border-outline"
    >
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("proxyColName")}</TableHead>
            <TableHead>{t("proxyColScheme")}</TableHead>
            <TableHead>{t("proxyColAddress")}</TableHead>
            <TableHead>{t("proxyColCountry")}</TableHead>
            <TableHead>{t("proxyColCity")}</TableHead>
            <TableHead>{t("proxyColStatus")}</TableHead>
            <TableHead>{t("proxyColUsedBy")}</TableHead>
            <TableHead>{t("proxyColActions")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {proxies.map((proxy) => {
            const id = proxy.id;
            const blocked = proxy.used_by_count > 0;
            const isTesting =
              probingId === id || proxy.observation_status === "pending";
            const count = proxy.used_by_count;
            const label = usedByLabel(count, t);

            return (
              <TableRow key={id} data-testid={`proxy-row-${id}`}>
                <TableCell>
                  <div className="flex items-center gap-xs">
                    <span className="font-ui text-body-md text-on-surface">
                      {proxy.name}
                    </span>
                    {proxy.notes && (
                      <Tooltip content={proxy.notes}>
                        <span
                          data-testid={`proxy-note-trigger-${id}`}
                          aria-label={proxy.notes}
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
                  <ProtocolChip protocol={proxy.scheme} />
                </TableCell>
                <TableCell>
                  <MonoValue>{`${proxy.host}:${proxy.port}`}</MonoValue>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-xs">
                    {proxy.country_code ? (
                      <RegionCode code={proxy.country_code} />
                    ) : null}
                    <span className="font-ui text-body-sm text-on-surface">
                      {proxy.country_name ?? proxy.country_code ?? "—"}
                    </span>
                  </div>
                </TableCell>
                <TableCell>
                  <span className="font-ui text-body-sm text-on-surface">
                    {proxy.city ?? "—"}
                  </span>
                </TableCell>
                <TableCell>
                  {proxy.observation_status === "pending" ? (
                    <span className="font-ui text-body-sm text-on-surface-muted">
                      {t("proxyStatusPending")}
                    </span>
                  ) : proxy.observation_status === "ok" ? (
                    <span
                      data-testid={`proxy-status-${id}`}
                      className="font-ui text-body-sm text-success"
                    >
                      {proxy.latency_ms != null
                        ? `${proxy.latency_ms}ms`
                        : t("proxyAvailable")}
                    </span>
                  ) : proxy.observation_status === "failed" ? (
                    <span
                      data-testid={`proxy-status-${id}`}
                      className="font-ui text-body-sm text-danger"
                    >
                      {proxy.observation_error_code ?? t("proxyProbeFailed")}
                    </span>
                  ) : (
                    <span className="font-ui text-body-sm text-on-surface-muted">
                      {t("proxyStatusUnknown")}
                    </span>
                  )}
                </TableCell>
                <TableCell>
                  {count === 0 ? (
                    <span
                      data-testid={`proxy-used-by-${id}`}
                      className="font-ui text-body-sm text-on-surface-muted"
                    >
                      {label}
                    </span>
                  ) : (
                    <button
                      type="button"
                      data-testid={`proxy-used-by-${id}`}
                      onClick={() => onUsedByClick(proxy)}
                      className="font-ui text-body-sm text-accent hover:underline"
                    >
                      {label}
                    </button>
                  )}
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap items-center gap-xs">
                    <IconButton
                      data-testid={`proxy-probe-${id}`}
                      label={t("proxyProbe")}
                      disabled={isTesting}
                      onClick={() => onProbe(proxy)}
                    >
                      <Zap
                        aria-hidden="true"
                        className="size-(--component-icon-md-size)"
                      />
                    </IconButton>
                    <IconButton
                      data-testid={`proxy-edit-${id}`}
                      label={t("proxyEdit")}
                      onClick={() => onEdit(proxy)}
                    >
                      <Pencil
                        aria-hidden="true"
                        className="size-(--component-icon-md-size)"
                      />
                    </IconButton>
                    {blocked ? (
                      <Tooltip content={t("proxyDeleteBlocked")}>
                        <span className="inline-flex items-center gap-xs">
                          <IconButton
                            variant="danger"
                            data-testid={`proxy-delete-${id}`}
                            label={t("proxyDelete")}
                            disabled
                          >
                            <Trash2
                              aria-hidden="true"
                              className="size-(--component-icon-md-size)"
                            />
                          </IconButton>
                          <span
                            data-testid={`proxy-delete-blocked-${id}`}
                            className="sr-only"
                          >
                            {t("proxyDeleteBlocked")}
                          </span>
                        </span>
                      </Tooltip>
                    ) : (
                      <IconButton
                        variant="danger"
                        data-testid={`proxy-delete-${id}`}
                        label={t("proxyDelete")}
                        onClick={() => onDelete(proxy)}
                      >
                        <Trash2
                          aria-hidden="true"
                          className="size-(--component-icon-md-size)"
                        />
                      </IconButton>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
