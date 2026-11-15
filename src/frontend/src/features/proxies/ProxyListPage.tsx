import { useMemo, useState } from "react";
import { Link } from "react-router";
import { AlertCircle, Pencil, Trash2, Zap } from "lucide-react";
import { useI18n } from "../../i18n";
import { ApiError } from "../../shared/api/client";
import { useApiClient } from "../../shared/api/client_context";
import type { ProxyResponse } from "../../shared/api/types";
import {
  Banner,
  Button,
  EmptyState,
  IconButton,
  MonoValue,
  ProtocolChip,
  RegionCode,
  StatusBadge,
  Tooltip,
  useToast,
} from "../../shared/ui";
import {
  useDeleteProxyMutation,
  useProbeProxyMutation,
  useProxiesQuery,
} from "../profiles/useProfilesQuery";
import { ProxyFormDialog } from "./ProxyFormDialog";
import {
  ProxyListToolbar,
  type ProxyLayout,
  type ProxySchemeFilter,
} from "./ProxyListToolbar";
import { ProxyTable, type ProxySpeedResult } from "./ProxyTable";

export function filterProxies(
  proxies: ProxyResponse[],
  query: string,
  scheme: ProxySchemeFilter,
  region = "all",
): ProxyResponse[] {
  const q = query.trim().toLowerCase();
  return proxies.filter((proxy) => {
    if (scheme !== "all" && proxy.scheme !== scheme) return false;
    if (region !== "all") {
      const proxyRegion = (
        proxy.country_code ||
        proxy.region_label ||
        ""
      ).trim();
      if (proxyRegion !== region) return false;
    }
    if (!q) return true;
    return [proxy.name, proxy.host, proxy.region_label ?? ""].some((value) =>
      value.toLowerCase().includes(q),
    );
  });
}

function proxyInUseCount(error: unknown): number | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  if (error.errorCode !== "proxy_in_use") return null;
  const data = error.data as { details?: unknown } | null | undefined;
  for (const candidate of [error.details, data?.details]) {
    if (candidate && typeof candidate === "object" && !Array.isArray(candidate)) {
      const usedByCount = (candidate as { used_by_count?: unknown }).used_by_count;
      if (typeof usedByCount === "number") return usedByCount;
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
  const [probingAll, setProbingAll] = useState(false);
  const [speedResults, setSpeedResults] = useState<
    Record<string, ProxySpeedResult>
  >({});

  const [query, setQuery] = useState("");
  const [scheme, setScheme] = useState<ProxySchemeFilter>("all");
  const [region, setRegion] = useState("all");
  const [layout, setLayout] = useState<ProxyLayout>("list");
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ProxyResponse | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ProxyResponse | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const regionOptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const proxy of proxies) {
      const key = (proxy.country_code || proxy.region_label || "").trim();
      if (!key) continue;
      const label =
        proxy.country_code && proxy.region_label
          ? `${proxy.country_code} · ${proxy.region_label}`
          : key;
      if (!map.has(key)) map.set(key, label);
    }
    return Array.from(map.entries()).map(([value, label]) => ({
      value,
      label,
    }));
  }, [proxies]);

  const visible = filterProxies(proxies, query, scheme, region);
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
    const startedAt = Date.now();
    setProbingId(proxy.id);
    setSpeedResults((prev) => ({
      ...prev,
      [proxy.id]: { status: "testing" },
    }));
    probeMutation.mutate(proxy.id, {
      onSuccess: () => {
        const elapsed = Math.max(12, Date.now() - startedAt);
        setSpeedResults((prev) => ({
          ...prev,
          [proxy.id]: { status: "ok", ms: elapsed },
        }));
        toast.show(t("proxyProbeSuccess"));
        setProbingId(null);
      },
      onError: (error: Error) => {
        setSpeedResults((prev) => ({
          ...prev,
          [proxy.id]: { status: "failed" },
        }));
        toast.show(`${t("proxyProbeFailed")}: ${error.message}`);
        setProbingId(null);
      },
    });
  };

  const handleProbeAll = async () => {
    if (visible.length === 0 || probingAll) return;
    setProbingAll(true);
    setSpeedResults((prev) => {
      const next = { ...prev };
      for (const item of visible) {
        next[item.id] = { status: "testing" };
      }
      return next;
    });
    for (const item of visible) {
      const startedAt = Date.now();
      try {
        await probeMutation.mutateAsync(item.id);
        const elapsed = Math.max(12, Date.now() - startedAt);
        setSpeedResults((prev) => ({
          ...prev,
          [item.id]: { status: "ok", ms: elapsed },
        }));
      } catch {
        setSpeedResults((prev) => ({
          ...prev,
          [item.id]: { status: "failed" },
        }));
      }
    }
    setProbingAll(false);
    toast.show(t("proxyProbeAllSuccess", { count: visible.length }));
  };

  return (
    <div data-testid="proxy-list-page" className="flex flex-col gap-md">
      <ProxyListToolbar
        query={query}
        onQueryChange={setQuery}
        scheme={scheme}
        onSchemeChange={setScheme}
        region={region}
        onRegionChange={setRegion}
        regions={regionOptions}
        layout={layout}
        onLayoutChange={setLayout}
        onProbeAll={() => void handleProbeAll()}
        probingAll={probingAll}
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
        <p
          data-testid="proxy-list-empty-error"
          className="font-ui text-body-sm text-danger"
        >
          {loadError}
        </p>
      ) : visible.length === 0 ? (
        <EmptyState title={t("proxyEmpty")} />
      ) : layout === "card" ? (
        <div
          data-testid="proxy-card-grid"
          className="grid grid-cols-1 gap-md md:grid-cols-2 lg:grid-cols-3"
        >
          {visible.map((proxy) => {
            const id = proxy.id;
            const blocked = proxy.used_by_count > 0;
            const speed = speedResults[id];
            const isTesting =
              probingId === id ||
              speed?.status === "testing" ||
              proxy.observation_status === "pending";
            return (
              <div
                key={id}
                data-testid={`proxy-card-${id}`}
                className="flex flex-col justify-between gap-sm rounded-lg border border-outline bg-surface p-md"
              >
                <div className="flex items-start justify-between gap-sm">
                  <div className="flex items-center gap-xs">
                    <span className="font-ui text-body-md text-on-surface">
                      {proxy.name}
                    </span>
                    {proxy.notes && (
                      <Tooltip content={proxy.notes}>
                        <span
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
                  <ProtocolChip protocol={proxy.scheme} />
                </div>
                <MonoValue>{`${proxy.host}:${proxy.port}`}</MonoValue>
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
                </div>
                <div className="flex items-center justify-between gap-sm border-t border-outline pt-sm">
                  <Link
                    to={`/?proxy=${encodeURIComponent(id)}`}
                    data-testid={`proxy-used-by-${id}`}
                    className="inline-flex items-center gap-xs font-ui text-body-sm text-accent hover:underline"
                  >
                    <MonoValue>{proxy.used_by_count}</MonoValue>
                    <span>{t("proxyUsedByLink")}</span>
                  </Link>
                  <div className="flex items-center gap-xs">
                    <IconButton
                      data-testid={`proxy-probe-${id}`}
                      label={t("proxyProbe")}
                      disabled={isTesting}
                      onClick={() => handleProbe(proxy)}
                    >
                      <Zap
                        aria-hidden="true"
                        className="size-(--component-icon-md-size)"
                      />
                    </IconButton>
                    <IconButton
                      data-testid={`proxy-edit-${id}`}
                      label={t("proxyEdit")}
                      onClick={() => openEdit(proxy)}
                    >
                      <Pencil
                        aria-hidden="true"
                        className="size-(--component-icon-md-size)"
                      />
                    </IconButton>
                    <IconButton
                      data-testid={`proxy-delete-${id}`}
                      label={t("proxyDelete")}
                      disabled={blocked}
                      onClick={() => requestDelete(proxy)}
                    >
                      <Trash2
                        aria-hidden="true"
                        className="size-(--component-icon-md-size)"
                      />
                    </IconButton>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <ProxyTable
          proxies={visible}
          onEdit={openEdit}
          onDelete={requestDelete}
          onProbe={handleProbe}
          probingId={probingId}
          speedResults={speedResults}
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
