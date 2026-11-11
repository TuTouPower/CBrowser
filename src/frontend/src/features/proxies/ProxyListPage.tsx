import { useState } from "react";
import { useI18n } from "../../i18n";
import { ApiError } from "../../shared/api/client";
import { useApiClient } from "../../shared/api/client_context";
import type { ProxyResponse } from "../../shared/api/types";
import { Banner, Button, EmptyState, useToast } from "../../shared/ui";
import {
  useDeleteProxyMutation,
  useProbeProxyMutation,
  useProxiesQuery,
} from "../profiles/useProfilesQuery";
import { ProxyFormDialog } from "./ProxyFormDialog";
import {
  ProxyListToolbar,
  type ProxySchemeFilter,
} from "./ProxyListToolbar";
import { ProxyTable } from "./ProxyTable";

export function filterProxies(
  proxies: ProxyResponse[],
  query: string,
  scheme: ProxySchemeFilter,
): ProxyResponse[] {
  const q = query.trim().toLowerCase();
  return proxies.filter((proxy) => {
    if (scheme !== "all" && proxy.scheme !== scheme) return false;
    if (!q) return true;
    return [proxy.name, proxy.host, proxy.region_label ?? ""].some((value) =>
      value.toLowerCase().includes(q),
    );
  });
}

function proxyInUseCount(error: unknown): number | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const data = error.data as { detail?: unknown } | null | undefined;
  for (const candidate of [error.detail, data?.detail]) {
    if (candidate && typeof candidate === "object") {
      const detail = candidate as { code?: unknown; used_by_count?: unknown };
      if (
        detail.code === "proxy_in_use" &&
        typeof detail.used_by_count === "number"
      ) {
        return detail.used_by_count;
      }
    }
  }
  return null;
}

export function ProxyListPage() {
  const { t } = useI18n();
  const client = useApiClient();
  const toast = useToast();
  const proxiesQuery = useProxiesQuery(client);
  const proxies = proxiesQuery.data ?? [];
  const deleteMutation = useDeleteProxyMutation(client);
  const probeMutation = useProbeProxyMutation(client);
  const [probingId, setProbingId] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [scheme, setScheme] = useState<ProxySchemeFilter>("all");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ProxyResponse | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ProxyResponse | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const visible = filterProxies(proxies, query, scheme);
  const loadError = proxiesQuery.isError
    ? (proxiesQuery.error?.message ?? t("runtimeStateUnknown"))
    : null;

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };

  const openEdit = (proxy: ProxyResponse) => {
    setEditing(proxy);
    setFormOpen(true);
  };

  const requestDelete = (proxy: ProxyResponse) => {
    setDeleteError(null);
    setDeleteTarget(proxy);
  };

  const cancelDelete = () => {
    setDeleteTarget(null);
    setDeleteError(null);
  };

  const confirmDelete = () => {
    if (!deleteTarget) return;
    deleteMutation.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast.show(t("proxyDeleteSuccess"));
        setDeleteTarget(null);
        setDeleteError(null);
      },
      onError: (error: Error) => {
        const count = proxyInUseCount(error);
        setDeleteError(
          count === null ? error.message : t("proxyInUse", { count }),
        );
        setDeleteTarget(null);
      },
    });
  };

  const handleProbe = (proxy: ProxyResponse) => {
    setProbingId(proxy.id);
    probeMutation.mutate(proxy.id, {
      onSuccess: () => {
        toast.show(t("proxyProbeSuccess"));
        setProbingId(null);
      },
      onError: (error: Error) => {
        toast.show(`${t("proxyProbeFailed")}: ${error.message}`);
        setProbingId(null);
      },
    });
  };

  return (
    <div data-testid="proxy-list-page" className="flex flex-col gap-lg p-lg">
      <ProxyListToolbar
        query={query}
        onQueryChange={setQuery}
        scheme={scheme}
        onSchemeChange={setScheme}
        onAdd={openCreate}
      />

      {loadError && (
        <Banner tone="danger" testId="proxy-list-load-error">
          <span>{loadError}</span>
          <Button
            size="sm"
            data-testid="proxy-list-retry"
            onClick={() => void proxiesQuery.refetch()}
          >
            {t("retryAction")}
          </Button>
        </Banner>
      )}

      {deleteError && (
        <Banner
          tone="danger"
          testId="proxy-list-error"
          onDismiss={() => setDeleteError(null)}
        >
          {deleteError}
        </Banner>
      )}

      {deleteTarget && (
        <div
          data-testid="proxy-delete-banner"
          className="flex flex-col gap-sm"
        >
          <Banner tone="danger">
            {`${t("proxyConfirmDelete")} · ${deleteTarget.name}`}
          </Banner>
          <div className="flex flex-wrap items-center gap-sm">
            <Button
              data-testid="proxy-delete-confirm"
              size="sm"
              variant="danger"
              onClick={confirmDelete}
            >
              {t("proxyConfirmDelete")}
            </Button>
            <Button
              data-testid="proxy-delete-cancel"
              size="sm"
              onClick={cancelDelete}
            >
              {t("proxyCancel")}
            </Button>
          </div>
        </div>
      )}

      {proxiesQuery.isPending ? (
        <p className="font-ui text-body-md text-on-surface-muted">
          {t("loading")}
        </p>
      ) : loadError && visible.length === 0 ? (
        // P2: 加载失败的空表不再渲染空 Table，保留顶栏错误 Banner 即错误态。
        <p
          data-testid="proxy-list-empty-error"
          className="font-ui text-body-sm text-danger"
        >
          {loadError}
        </p>
      ) : visible.length === 0 ? (
        <EmptyState title={t("proxyEmpty")} />
      ) : (
        <ProxyTable
          proxies={visible}
          onEdit={openEdit}
          onDelete={requestDelete}
          onProbe={handleProbe}
          probingId={probingId}
        />
      )}

      <ProxyFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        proxy={editing}
      />
    </div>
  );
}
