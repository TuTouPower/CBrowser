import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { useRuntimeSnapshot } from "../../app/useRuntimeSnapshot";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import type {
  ProfileResponse,
  ProfileRuntimeResponse,
  RuntimeSummaryEntry,
} from "../../shared/api/types";
import { Banner, Button, useToast } from "../../shared/ui";
import { BatchActionBar } from "./BatchActionBar";
import { EnvironmentCardGrid } from "./EnvironmentCardGrid";
import { EnvironmentEmptyState } from "./EnvironmentEmptyState";
import { EnvironmentListToolbar } from "./EnvironmentListToolbar";
import {
  EnvironmentTable,
  type EnvironmentAction,
  type EnvironmentRow,
} from "./EnvironmentTable";
import { GroupManagerDialog } from "./GroupManagerDialog";
import { ProfileCreateDialog } from "./ProfileCreateDialog";
import { ProfileEditDialog } from "./ProfileEditDialog";
import { useBatchActions } from "./useBatchActions";
import {
  isFiltered,
  useEnvironmentFilters,
} from "./useEnvironmentFilters";
import { useEnvironmentLayout } from "./useEnvironmentLayout";
import {
  useDeleteProfileMutation,
  useDuplicateProfileMutation,
  useGroupCandidatesQuery,
  useGroupQuery,
  useProfilesCollectionQuery,
  useProxyCandidatesQuery,
  useProxyQuery,
  useRuntimeSummaryQuery,
  useSetDesiredStateMutation,
  useStopProfileMutation,
} from "./useProfilesQuery";

/** t076 AC-002: build the row runtime view from one batched summary
 * entry — the list never issues a per-profile runtime request. */
function summaryToRuntime(
  entry: RuntimeSummaryEntry,
  profile: ProfileResponse,
): ProfileRuntimeResponse {
  return {
    profile_id: entry.profile_id,
    display_number: profile.display_number,
    desired_state: entry.desired_state,
    observed_state: entry.observed_state,
    runtime_instance_id: entry.runtime_instance_id ?? null,
    config_version: entry.config_version,
    failure_count: entry.failure_count,
    restart_blocked: entry.restart_blocked,
    last_exit_event_id: null,
    last_started_at: entry.last_started_at,
    last_stopped_at: entry.last_stopped_at,
    preview_captured_at: entry.preview_captured_at ?? null,
    last_coordinator_error: entry.last_coordinator_error,
    updated_at: entry.updated_at,
  };
}

export function EnvironmentListPage() {
  const { t } = useI18n();
  const client = useApiClient();
  const navigate = useNavigate();
  const toast = useToast();
  const { filters, setFilter, clearFilters } = useEnvironmentFilters();
  const [layout, setLayout] = useEnvironmentLayout();
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  // t076 AC-001: server-side paging (50/page); the page resets whenever
  // any filter changes, so a filtered view never strands on an empty
  // page. Header select-all below is page-scoped by definition.
  const [page, setPage] = useState(1);
  useEffect(() => {
    setPage(1);
  }, [
    filters.q,
    filters.status,
    filters.group,
    filters.platform,
    filters.proxy,
    filters.sort,
  ]);
  const [createOpen, setCreateOpen] = useState(false);
  const [editingRow, setEditingRow] = useState<EnvironmentRow | null>(null);
  const [groupsOpen, setGroupsOpen] = useState(false);
  const [moveMenuOpen, setMoveMenuOpen] = useState(false);
  // P2: 单删 / 批量删除二次确认，避免误触。
  const [pendingDeleteRow, setPendingDeleteRow] = useState<EnvironmentRow | null>(null);
  const [confirmingBatchDelete, setConfirmingBatchDelete] = useState(false);

  const profilesQuery = useProfilesCollectionQuery(
    {
      search: filters.q || undefined,
      group_id: filters.group === "all" ? undefined : filters.group,
      proxy_id: filters.proxy === "all" ? undefined : filters.proxy,
      status: filters.status === "all" ? undefined : filters.status,
      platform: filters.platform === "all" ? undefined : filters.platform,
      sort: filters.sort === "manual" ? "default" : filters.sort,
      page,
      page_size: 50,
    },
    client,
  );
  // t076 review f006: filter options and the move menu read the
  // bounded candidate endpoints, never the whole group/proxy tables.
  // The selected filter value is fetched on its own when it falls
  // outside the first candidate page (e.g. a bookmarked filter URL),
  // so the select keeps showing it.
  const groupsQuery = useGroupCandidatesQuery("", 50, client);
  const proxiesQuery = useProxyCandidatesQuery("", 50, client);
  const selectedGroupId =
    filters.group !== "all" && filters.group !== "ungrouped"
      ? filters.group
      : null;
  const selectedProxyId =
    filters.proxy !== "all" && filters.proxy !== "direct"
      ? filters.proxy
      : null;
  const selectedGroupQuery = useGroupQuery(selectedGroupId, client);
  const selectedProxyQuery = useProxyQuery(selectedProxyId, client);
  const summaryQuery = useRuntimeSummaryQuery(client);
  const profiles = profilesQuery.data?.items ?? [];
  const total = profilesQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / 50));
  const groups = [
    ...(groupsQuery.data ?? []),
    ...(selectedGroupQuery.data &&
    !(groupsQuery.data ?? []).some(
      (item) => item.id === selectedGroupQuery.data!.id,
    )
      ? [selectedGroupQuery.data]
      : []),
  ];
  const proxies = [
    ...(proxiesQuery.data ?? []),
    ...(selectedProxyQuery.data &&
    !(proxiesQuery.data ?? []).some(
      (item) => item.id === selectedProxyQuery.data!.id,
    )
      ? [selectedProxyQuery.data]
      : []),
  ];
  const snapshot = useRuntimeSnapshot(client);

  const summaryById = new Map(
    (summaryQuery.data?.entries ?? []).map((entry) => [
      entry.profile_id,
      entry,
    ]),
  );
  const runtimeById = new Map<string, ProfileRuntimeResponse | undefined>();
  profiles.forEach((item) => {
    const entry = summaryById.get(item.id);
    runtimeById.set(
      item.id,
      entry ? summaryToRuntime(entry, item) : undefined,
    );
  });

  const previewCapturedAtById = new Map<string, string | null>();
  profiles.forEach((item) => {
    previewCapturedAtById.set(
      item.id,
      runtimeById.get(item.id)?.preview_captured_at ?? null,
    );
  });

  // t076 AC-001: search/filter/sort already ran server-side against the
  // full set; the rows below are exactly the current page.
  // t076 review f006: the row's group/proxy names travel with the
  // collection page — no whole-table lookup to name a row.
  const visibleRows: EnvironmentRow[] = profiles.map((item) => ({
    profile: item,
    runtime: runtimeById.get(item.id),
    group:
      item.group_id && item.group_name
        ? {
            id: item.group_id,
            name: item.group_name,
            color: item.group_color ?? "slate",
          }
        : undefined,
    proxy:
      item.proxy_id && item.proxy_name
        ? { id: item.proxy_id, name: item.proxy_name }
        : undefined,
  }));

  const toggle = useCallback((id: string, checked: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(
    (checked: boolean) => {
      setSelected((prev) => {
        const next = new Set(prev);
        for (const row of visibleRows) {
          if (checked) next.add(row.profile.id);
          else next.delete(row.profile.id);
        }
        return next;
      });
    },
    [visibleRows],
  );

  const clearSelection = useCallback((succeededIds: string[]) => {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of succeededIds) next.delete(id);
      return next;
    });
  }, []);

  const { run, pending } = useBatchActions({
    selected,
    rows: visibleRows,
    clearSelection,
  });

  const startMutation = useSetDesiredStateMutation(client);
  const stopMutation = useStopProfileMutation(client);
  const duplicateMutation = useDuplicateProfileMutation(client);
  const deleteMutation = useDeleteProfileMutation(client);

  const handleAction = useCallback(
    (action: EnvironmentAction, row: EnvironmentRow) => {
      const id = row.profile.id;
      const onError = (error: Error) => toast.show(error.message);
      switch (action) {
        case "open":
          navigate(`/session/${id}`);
          break;
        case "start":
          startMutation.mutate({ id, state: "running" }, { onError });
          break;
        case "stop":
          stopMutation.mutate(id, { onError });
          break;
        case "details":
          navigate(`/profiles/${id}/config`);
          break;
        case "edit":
          setEditingRow(row);
          break;
        case "duplicate":
          duplicateMutation.mutate(
            { id, includeBrowserState: false },
            { onError },
          );
          break;
        case "delete":
          // P2: 单删需二次确认，实际删除走确认框。
          setPendingDeleteRow(row);
          break;
      }
    },
    [
      navigate,
      toast,
      clearSelection,
      startMutation,
      stopMutation,
      duplicateMutation,
      deleteMutation,
    ],
  );

  const handleMove = (groupId: string | null) => {
    setMoveMenuOpen(false);
    void run("moveToGroup", { groupId });
  };

  const profilesError = profilesQuery.isError
    ? (profilesQuery.error?.message ?? t("runtimeStateUnknown"))
    : null;
  const runtimeError = summaryQuery.isError
    ? (summaryQuery.error?.message ?? t("runtimeStateUnknown"))
    : null;
  // P2: groups/proxies 聚合进列表错误态，避免静默空列表。
  const groupsError = groupsQuery.isError
    ? (groupsQuery.error?.message ?? t("runtimeStateUnknown"))
    : null;
  const proxiesError = proxiesQuery.isError
    ? (proxiesQuery.error?.message ?? t("runtimeStateUnknown"))
    : null;
  const listError = profilesError ?? runtimeError ?? groupsError ?? proxiesError;
  const reloadList = () => {
    if (profilesQuery.isError) void profilesQuery.refetch();
    if (summaryQuery.isError) void summaryQuery.refetch();
    if (groupsQuery.isError) void groupsQuery.refetch();
    if (proxiesQuery.isError) void proxiesQuery.refetch();
  };

  const confirmSingleDelete = () => {
    if (!pendingDeleteRow) return;
    const id = pendingDeleteRow.profile.id;
    const onError = (error: Error) => toast.show(error.message);
    deleteMutation.mutate(id, {
      onSuccess: () => {
        clearSelection([id]);
        setPendingDeleteRow(null);
      },
      onError,
    });
  };

  const confirmBatchDelete = () => {
    setConfirmingBatchDelete(false);
    void run("delete");
  };

  return (
    <div
      data-testid="env-list-page"
      className="flex flex-col gap-lg p-lg"
    >
      <EnvironmentListToolbar
        filters={filters}
        setFilter={setFilter}
        layout={layout}
        setLayout={setLayout}
        onNew={() => setCreateOpen(true)}
        onManageGroups={() => setGroupsOpen(true)}
        groups={groups}
        proxies={proxies}
        onClearFilters={clearFilters}
      />
      {listError && (
        <Banner tone="danger" testId="env-list-error">
          <span>{listError}</span>
          <Button size="sm" data-testid="env-list-retry" onClick={reloadList}>
            {t("retryAction")}
          </Button>
        </Banner>
      )}
      <div
        data-testid="env-running-count"
        className="inline-flex items-center gap-xs font-ui text-label-sm text-on-surface-muted"
      >
        <span
          aria-hidden="true"
          className="size-(--component-group-chip-size) rounded-full bg-success"
        />
        {t("runningProfiles", { count: snapshot.runningCount })}
      </div>

      {profilesQuery.isPending ? (
        <p className="font-ui text-body-md text-on-surface-muted">
          {t("loading")}
        </p>
      ) : visibleRows.length === 0 && !profilesError ? (
        <EnvironmentEmptyState
          filtered={isFiltered(filters)}
          onNew={() => setCreateOpen(true)}
          onClearFilters={clearFilters}
        />
      ) : layout === "list" ? (
        <EnvironmentTable
          rows={visibleRows}
          selected={selected}
          onToggle={toggle}
          onToggleAll={toggleAll}
          onAction={handleAction}
        />
      ) : (
        <EnvironmentCardGrid
          rows={visibleRows}
          selected={selected}
          onToggle={toggle}
          onAction={handleAction}
          previewCapturedAtById={previewCapturedAtById}
        />
      )}

      {totalPages > 1 && (
        <div
          data-testid="env-list-pager"
          className="flex items-center gap-sm font-ui text-body-md text-on-surface"
        >
          <Button
            size="sm"
            data-testid="env-list-prev-page"
            disabled={page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            {t("pagePrev")}
          </Button>
          <span data-testid="env-list-page-status">
            {t("pageStatus", { page, pages: totalPages, total })}
          </span>
          <Button
            size="sm"
            data-testid="env-list-next-page"
            disabled={page >= totalPages}
            onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
          >
            {t("pageNext")}
          </Button>
        </div>
      )}

      {selected.size > 0 && (
        <>
          <BatchActionBar
            count={selected.size}
            onStart={() => void run("start")}
            onStop={() => void run("stop")}
            onMove={() => setMoveMenuOpen(true)}
            onDelete={() => setConfirmingBatchDelete(true)}
            pending={pending}
          />
          {confirmingBatchDelete && (
            <div
              data-testid="env-batch-delete-confirm"
              className="fixed bottom-2xl left-1/2 z-40 flex -translate-x-1/2 flex-wrap items-center gap-sm rounded-lg border border-outline bg-surface-raised px-md py-sm shadow-lg"
            >
              <span className="font-ui text-body-sm text-on-surface">
                {t("envBatchDeleteConfirm", { count: selected.size })}
              </span>
              <Button
                data-testid="env-batch-delete-accept"
                size="sm"
                variant="danger"
                disabled={pending}
                onClick={confirmBatchDelete}
              >
                {t("envBatchDelete")}
              </Button>
              <Button
                data-testid="env-batch-delete-cancel"
                size="sm"
                onClick={() => setConfirmingBatchDelete(false)}
              >
                {t("cancel")}
              </Button>
            </div>
          )}
          {moveMenuOpen && (
            <div
              data-testid="env-move-menu"
              className="fixed bottom-2xl left-1/2 z-40 flex -translate-x-1/2 flex-wrap items-center gap-sm rounded-lg border border-outline bg-surface-raised px-md py-sm shadow-lg"
            >
              {groups.map((item) => (
                <Button
                  key={item.id}
                  data-testid={`env-move-group-${item.id}`}
                  size="sm"
                  onClick={() => handleMove(item.id)}
                >
                  {item.name}
                </Button>
              ))}
              <Button
                data-testid="env-move-ungrouped"
                size="sm"
                onClick={() => handleMove(null)}
              >
                {t("envFilterUngrouped")}
              </Button>
            </div>
          )}
        </>
      )}

      <ProfileCreateDialog open={createOpen} onOpenChange={setCreateOpen} />
      <ProfileEditDialog
        open={editingRow !== null}
        profile={editingRow?.profile ?? null}
        onOpenChange={(open) => {
          if (!open) setEditingRow(null);
        }}
      />
      <GroupManagerDialog open={groupsOpen} onOpenChange={setGroupsOpen} />
      {pendingDeleteRow && (
        <div
          data-testid="env-delete-confirm"
          className="fixed bottom-2xl left-1/2 z-40 flex -translate-x-1/2 flex-wrap items-center gap-sm rounded-lg border border-outline bg-surface-raised px-md py-sm shadow-lg"
        >
          <span className="font-ui text-body-sm text-on-surface">
            {t("envDeleteConfirm", { name: pendingDeleteRow.profile.name })}
          </span>
          <Button
            data-testid="env-delete-accept"
            size="sm"
            variant="danger"
            disabled={deleteMutation.isPending}
            onClick={confirmSingleDelete}
          >
            {t("envDelete")}
          </Button>
          <Button
            data-testid="env-delete-cancel"
            size="sm"
            onClick={() => setPendingDeleteRow(null)}
          >
            {t("cancel")}
          </Button>
        </div>
      )}
    </div>
  );
}
