import { useCallback, useState } from "react";
import { useNavigate } from "react-router";
import { useQueries } from "@tanstack/react-query";
import { useRuntimeSnapshot } from "../../app/useRuntimeSnapshot";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import type { ProfileRuntimeResponse } from "../../shared/api/types";
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
import { useBatchActions } from "./useBatchActions";
import {
  filterEnvironmentRows,
  isFiltered,
  sortEnvironmentRows,
  useEnvironmentFilters,
} from "./useEnvironmentFilters";
import { useEnvironmentLayout } from "./useEnvironmentLayout";
import {
  profileKeys,
  useDeleteProfileMutation,
  useDuplicateProfileMutation,
  useGroupsQuery,
  useProfilesQuery,
  useProxiesQuery,
  useSetDesiredStateMutation,
  useStopProfileMutation,
} from "./useProfilesQuery";

export function EnvironmentListPage() {
  const { t } = useI18n();
  const client = useApiClient();
  const navigate = useNavigate();
  const toast = useToast();
  const { filters, setFilter, clearFilters } = useEnvironmentFilters();
  const [layout, setLayout] = useEnvironmentLayout();
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [createOpen, setCreateOpen] = useState(false);
  const [groupsOpen, setGroupsOpen] = useState(false);
  const [moveMenuOpen, setMoveMenuOpen] = useState(false);
  // P2: 单删 / 批量删除二次确认，避免误触。
  const [pendingDeleteRow, setPendingDeleteRow] = useState<EnvironmentRow | null>(null);
  const [confirmingBatchDelete, setConfirmingBatchDelete] = useState(false);

  const profilesQuery = useProfilesQuery(client);
  const groupsQuery = useGroupsQuery(client);
  const proxiesQuery = useProxiesQuery(client);
  const profiles = profilesQuery.data ?? [];
  const groups = groupsQuery.data ?? [];
  const proxies = proxiesQuery.data ?? [];
  const snapshot = useRuntimeSnapshot(client);

  const runtimeQueries = useQueries({
    queries: profiles.map((item) => ({
      queryKey: profileKeys.runtime(item.id),
      queryFn: () => client.profiles.getRuntime(item.id),
      // P2: 列表运行时查询加 enabled/staleTime，避免空转与抖动。
      enabled: profiles.length > 0,
      staleTime: 5000,
    })),
  });

  const runtimeById = new Map<string, ProfileRuntimeResponse | undefined>();
  profiles.forEach((item, index) => {
    runtimeById.set(
      item.id,
      runtimeQueries[index]?.data as ProfileRuntimeResponse | undefined,
    );
  });

  const previewCapturedAtById = new Map<string, string | null>();
  profiles.forEach((item) => {
    previewCapturedAtById.set(
      item.id,
      runtimeById.get(item.id)?.preview_captured_at ?? null,
    );
  });

  const rows: EnvironmentRow[] = profiles.map((item) => ({
    profile: item,
    runtime: runtimeById.get(item.id),
    group: groups.find((entry) => entry.id === item.group_id),
    proxy: proxies.find((entry) => entry.id === item.proxy_id),
  }));

  const visibleRows = sortEnvironmentRows(
    filterEnvironmentRows(rows, filters),
    filters.sort,
  );

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
    rows,
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
        case "edit":
          navigate(`/profiles/${id}/config`);
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
  const runtimeError = runtimeQueries.some((query) => query.isError)
    ? (runtimeQueries.find((query) => query.isError)?.error?.message ??
      t("runtimeStateUnknown"))
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
    for (const query of runtimeQueries) {
      if (query.isError) void query.refetch();
    }
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
        className="font-ui text-label-sm text-on-surface-muted"
      >
        {snapshot.runningCount}
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
