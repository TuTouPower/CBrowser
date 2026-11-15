import { Link } from "react-router";
import { AlertCircle, Pencil, Trash2, Zap } from "lucide-react";
import { useI18n } from "../../i18n";
import type { ProxyResponse } from "../../shared/api/types";
import {
  IconButton,
  MonoValue,
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
} from "../../shared/ui";

export interface ProxySpeedResult {
  status: "testing" | "ok" | "failed";
  ms?: number;
}

export interface ProxyTableProps {
  proxies: ProxyResponse[];
  onEdit: (proxy: ProxyResponse) => void;
  onDelete: (proxy: ProxyResponse) => void;
  onProbe: (proxy: ProxyResponse) => void;
  probingId?: string | null;
  speedResults?: Record<string, ProxySpeedResult>;
}

export function ProxyTable({
  proxies,
  onEdit,
  onDelete,
  onProbe,
  probingId,
  speedResults = {},
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
            <TableHead>{t("proxyColRegion")}</TableHead>
            <TableHead>{t("proxyColUsedBy")}</TableHead>
            <TableHead>{t("proxyColActions")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {proxies.map((proxy) => {
            const id = proxy.id;
            const blocked = proxy.used_by_count > 0;
            const speed = speedResults[id];
            const isTesting =
              probingId === id ||
              speed?.status === "testing" ||
              proxy.observation_status === "pending";

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
                  <div className="flex flex-wrap items-center gap-sm">
                    {isTesting ? (
                      <span className="font-ui text-body-sm text-on-surface-muted">
                        {t("proxyCountryProbing")}
                      </span>
                    ) : proxy.country_code ? (
                      <RegionCode code={proxy.country_code} />
                    ) : (
                      <span className="font-ui text-body-sm text-on-surface-muted">
                        {t("proxyCountryUnknown")}
                      </span>
                    )}
                    {proxy.region_label && (
                      <span className="font-ui text-body-sm text-on-surface">
                        {proxy.region_label}
                      </span>
                    )}
                    {speed?.status === "ok" && (
                      <StatusBadge
                        tone="running"
                        label={
                          speed.ms != null
                            ? `${t("proxyAvailable")} · ${speed.ms}ms`
                            : t("proxyAvailable")
                        }
                      />
                    )}
                    {speed?.status === "failed" && (
                      <StatusBadge tone="error" label={t("proxyProbeFailed")} />
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <Link
                    to={`/?proxy=${encodeURIComponent(id)}`}
                    data-testid={`proxy-used-by-${id}`}
                    className="inline-flex items-center gap-sm font-ui text-body-sm text-accent hover:underline"
                  >
                    <MonoValue>{proxy.used_by_count}</MonoValue>
                    <span>{t("proxyUsedByLink")}</span>
                  </Link>
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
