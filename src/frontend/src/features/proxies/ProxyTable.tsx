import { Link } from "react-router";
import { useI18n } from "../../i18n";
import type { ProxyResponse } from "../../shared/api/types";
import {
  Button,
  MonoValue,
  ProtocolChip,
  RegionCode,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../shared/ui";

export interface ProxyTableProps {
  proxies: ProxyResponse[];
  onEdit: (proxy: ProxyResponse) => void;
  onDelete: (proxy: ProxyResponse) => void;
}

export function ProxyTable({ proxies, onEdit, onDelete }: ProxyTableProps) {
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
            <TableHead>{t("proxyColAuth")}</TableHead>
            <TableHead>{t("proxyColRegion")}</TableHead>
            <TableHead>{t("proxyColUsedBy")}</TableHead>
            <TableHead>{t("proxyColActions")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {proxies.map((proxy) => {
            const id = proxy.id;
            const blocked = proxy.used_by_count > 0;
            return (
              <TableRow key={id} data-testid={`proxy-row-${id}`}>
                <TableCell>
                  <div className="flex flex-col gap-xs">
                    <span className="font-ui text-body-md text-on-surface">
                      {proxy.name}
                    </span>
                    {proxy.notes && (
                      <span className="font-ui text-label-sm text-on-surface-muted">
                        {proxy.notes}
                      </span>
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
                  <span className="font-ui text-body-sm text-on-surface">
                    {proxy.has_password ? t("proxyAuthYes") : t("proxyAuthNo")}
                  </span>
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap items-center gap-sm">
                    {proxy.country_code && (
                      <RegionCode code={proxy.country_code} />
                    )}
                    {proxy.region_label && (
                      <span className="font-ui text-body-sm text-on-surface">
                        {proxy.region_label}
                      </span>
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
                    <Button
                      data-testid={`proxy-edit-${id}`}
                      size="sm"
                      onClick={() => onEdit(proxy)}
                    >
                      {t("proxyEdit")}
                    </Button>
                    {blocked ? (
                      <span className="inline-flex flex-wrap items-center gap-xs">
                        <Button
                          data-testid={`proxy-delete-${id}`}
                          size="sm"
                          variant="danger"
                          disabled
                        >
                          {t("proxyDelete")}
                        </Button>
                        <span
                          data-testid={`proxy-delete-blocked-${id}`}
                          className="font-ui text-label-sm text-on-surface-muted"
                        >
                          {t("proxyDeleteBlocked")}
                        </span>
                      </span>
                    ) : (
                      <Button
                        data-testid={`proxy-delete-${id}`}
                        size="sm"
                        variant="danger"
                        onClick={() => onDelete(proxy)}
                      >
                        {t("proxyDelete")}
                      </Button>
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
