import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { AlertCircle, Pencil, Trash2, Zap } from "lucide-react";
import { useI18n } from "../../i18n";
import { ApiError } from "../../shared/api/client";
import { useApiClient } from "../../shared/api/client_context";
import type { ProxyResponse, ProxyUsedByEntry } from "../../shared/api/types";
import {
  Banner,
  Button,
  EmptyState,
  IconButton,
  MonoValue,
  ProtocolChip,
  RegionCode,
  Tooltip,
  useToast,
} from "../../shared/ui";
import {
  useDeleteProxyMutation,
  useProbeProxyMutation,
  useProxiesCollectionQuery,
  useProxyCountriesQuery,
} from "../profiles/useProfilesQuery";
import { ProxyFormDialog } from "./ProxyFormDialog";
import { ProxyListToolbar } from "./ProxyListToolbar";
import { ProxyTable } from "./ProxyTable";
import { ProxyUsedByPopover } from "./ProxyUsedByPopover";
import {
  useProxyFilters,
  type ProxyFilters,
} from "./useProxyFilters";
import { useProxyLayout } from "./useProxyLayout";

export function filterProxies(
  proxies: ProxyResponse[],
  filters: ProxyFilters,
): ProxyResponse[] {
  const q = filters.q.trim().toLowerCase();
  return proxies.filter((proxy) => {
    if (filters.scheme !== "all" && proxy.scheme !== filters.scheme) {
      return false;
    }
    if (filters.country !== "all") {
      const country = (proxy.country_name || proxy.country_code || "").trim();
      if (country !== filters.country) return false;
    }
    if (filters.city !== "all") {
      const city = (proxy.city || "").trim();
      if (city !== filters.city) return false;
    }
    if (!q) return true;
    return [
      proxy.name,
      proxy.host,
      proxy.country_name ?? "",
      proxy.city ?? "",
      proxy.region_label ?? "",
    ].some((value) => value.toLowerCase().includes(q));
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

function ProxyStatusText({ proxy }: { proxy: ProxyResponse }) {
  const { t } = useI18n();
  if (proxy.observation_status === "pending") {
    return (
      <span className="font-ui text-body-sm text-on-surface-muted">
        {t("proxyStatusPending")}
      </span>
    );
  }
  if (proxy.observation_status === "ok") {
    return (
      <span className="font-ui text-body-sm text-success">
        {proxy.latency_ms != null ? `${proxy.latency_ms}ms` : t("proxyAvailable")}
      </span>
    );
  }
  if (proxy.observation_status === "failed") {
    return (
      <span className="font-ui text-body-sm text-danger">
        {proxy.observation_error_code ?? t("proxyProbeFailed")}
      </span>
    );
  }
  return (
    <span className="font-ui text-body-sm text-on-surface-muted">
      {t("proxyStatusUnknown")}
    </span>
  );
}

function usedByLabel(
  count: number,
  t: ReturnType<typeof useI18n>["t"],
): string {
  return count === 1
    ? t("proxyUsedByCountOne")
    : t("proxyUsedByCount", { count });
}

export function ProxyListPage() {
  const { t } = useI18n();
  const client = useApiClient();
  const navigate = useNavigate();
  const toast = useToast();
  const { filters, setFilter, setFilters } = useProxyFilters();
  const [layout, setLayout] = useProxyLayout();
  // t076 AC-001: server-side collection page (50/page); the page resets
  // whenever any filter changes, so a filtered view never strands on an
  // empty page.
  const [page, setPage] = useState(1);
  useEffect(() => {
    setPage(1);
  }, [filters.q, filters.scheme, filters.country, filters.city]);
  const proxiesQuery = useProxiesCollectionQuery(
    {
      search: filters.q || undefined,
      scheme: filters.scheme === "all" ? undefined : filters.scheme,
      country_code: filters.country === "all" ? undefined : filters.country,
      city: filters.city === "all" ? undefined : filters.city,
      page,
      page_size: 50,
    },
    client,
  );
  const countriesQuery = useProxyCountriesQuery(client);
  const proxies = proxiesQuery.data?.items ?? [];
  const total = proxiesQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / 50));
  const ranges = countriesQuery.data ?? [];
  const deleteMutation = useDeleteProxyMutation(client);
  const probeMutation = useProbeProxyMutation(client);

  const [probingId, setProbingId] = useState<string | null>(null);
  const [probingAll, setProbingAll] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<ProxyResponse | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ProxyResponse | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [usedByTarget, setUsedByTarget] = useState<{
    proxy: ProxyResponse;
    entries: ProxyUsedByEntry[];
  } | null>(null);

  // t076 AC-001: country/city options come from the server ranges, keyed
  // by country code (the collection filter matches codes, not display
  // names). City options follow the selected country (t074 AC-005
  // linked filters); the country change still resets the city in one
  // setSearchParams call (see onCountryChange below).
  const countryOptions = useMemo(
    () =>
      ranges.map((range) => ({
        value: range.country_code,
        label: range.country_name || range.country_code,
      })),
    [ranges],
  );

  const cityOptions = useMemo(() => {
    const cities = new Set<string>();
    for (const range of ranges) {
      if (filters.country !== "all" && range.country_code !== filters.country) {
        continue;
      }
      for (const city of range.cities) cities.add(city);
    }
    return Array.from(cities).map((value) => ({ value, label: value }));
  }, [ranges, filters.country]);

  // t076 AC-001: search/filter already ran server-side against the full
  // set; visible is exactly the current page. (filterProxies stays
  // exported for its direct unit tests; the page no longer filters
  // client-side.)
  const visible = proxies;
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
      onSuccess: (updated: ProxyResponse) => {
        setProbingId(null);
        // HTTP 200 with observation_status=failed is a real failure
        // (t074 AC-004): never report success for it.
        if (updated.observation_status === "failed") {
          toast.show(t("proxyProbeFailed"));
          return;
        }
        toast.show(t("proxyProbeSuccess"));
      },
      onError: (error: Error) => {
        setProbingId(null);
        toast.show(`${t("proxyProbeFailed")}: ${error.message}`);
      },
    });
  };

  const handleProbeAll = async () => {
    if (visible.length === 0 || probingAll) return;
    setProbingAll(true);
    let failed = 0;
    for (const item of visible) {
      try {
        const updated = await probeMutation.mutateAsync(item.id);
        if (updated.observation_status === "failed") failed += 1;
      } catch {
        failed += 1;
      }
    }
    setProbingAll(false);
    if (failed > 0) {
      toast.show(`${t("proxyProbeFailed")} · ${failed}`);
      return;
    }
    toast.show(t("proxyProbeAllSuccess", { count: visible.length }));
  };

  // t076 AC-004: count, detail, navigation and delete protection all
  // use the backend union (current config ∪ running bound version).
  // The detail is fetched only when the user opens it; a single entry
  // navigates straight to that environment, several open the popover.
  const handleUsedByClick = async (proxy: ProxyResponse) => {
    if (proxy.used_by_count === 0) return;
    try {
      const detail = await client.proxies.getUsedBy(proxy.id);
      if (detail.entries.length === 1) {
        navigate(
          `/profiles/${encodeURIComponent(detail.entries[0]!.profile_id)}/config`,
        );
      } else if (detail.entries.length > 1) {
        setUsedByTarget({ proxy, entries: detail.entries });
      }
    } catch {
      toast.show(t("proxyUsedByLoadFailed"));
    }
  };

  const onUsedBySingle = (profile: { id: string }) => {
    navigate(`/profiles/${encodeURIComponent(profile.id)}/config`);
  };

  const onCountryChange = (value: string) => {
    setFilters({ country: value, city: "all" });
  };

  return (
    <div data-testid="proxy-list-page" className="flex flex-col gap-md">
      <ProxyListToolbar
        query={filters.q}
        onQueryChange={(value) => setFilter("q", value)}
        scheme={filters.scheme}
        onSchemeChange={(value) => setFilter("scheme", value)}
        country={filters.country}
        onCountryChange={onCountryChange}
        countries={countryOptions}
        city={filters.city}
        onCityChange={(value) => setFilter("city", value)}
        cities={cityOptions}
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
            const isTesting =
              probingId === id || proxy.observation_status === "pending";
            const count = proxy.used_by_count;
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
                  {proxy.country_code ? (
                    <RegionCode code={proxy.country_code} />
                  ) : null}
                  <span className="font-ui text-body-sm text-on-surface">
                    {proxy.country_name ?? proxy.country_code ?? "—"}
                  </span>
                  <span className="font-ui text-body-sm text-on-surface-muted">
                    {proxy.city ?? "—"}
                  </span>
                  <ProxyStatusText proxy={proxy} />
                </div>
                <div className="flex items-center justify-between gap-sm border-t border-outline pt-sm">
                  {count === 0 ? (
                    <span
                      data-testid={`proxy-used-by-${id}`}
                      className="font-ui text-body-sm text-on-surface-muted"
                    >
                      {usedByLabel(count, t)}
                    </span>
                  ) : (
                    <button
                      type="button"
                      data-testid={`proxy-used-by-${id}`}
                      onClick={() => void handleUsedByClick(proxy)}
                      className="font-ui text-body-sm text-accent hover:underline"
                    >
                      {usedByLabel(count, t)}
                    </button>
                  )}
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
                      variant="danger"
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
          onUsedByClick={(proxy) => void handleUsedByClick(proxy)}
        />
      )}

      {totalPages > 1 && (
        <div
          data-testid="proxy-list-pager"
          className="flex items-center gap-sm font-ui text-body-md text-on-surface"
        >
          <Button
            size="sm"
            data-testid="proxy-list-prev-page"
            disabled={page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            {t("pagePrev")}
          </Button>
          <span data-testid="proxy-list-page-status">
            {t("pageStatus", { page, pages: totalPages, total })}
          </span>
          <Button
            size="sm"
            data-testid="proxy-list-next-page"
            disabled={page >= totalPages}
            onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
          >
            {t("pageNext")}
          </Button>
        </div>
      )}

      <ProxyFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        proxy={editing}
      />

      {usedByTarget && (
        <ProxyUsedByPopover
          entries={usedByTarget.entries}
          open={usedByTarget.entries.length > 0}
          onOpenChange={(open) => {
            if (!open) setUsedByTarget(null);
          }}
          onOpenProfile={onUsedBySingle}
        />
      )}
    </div>
  );
}
