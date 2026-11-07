import { useCallback, useState } from "react";
import { useNavigate } from "react-router";
import { useQueries } from "@tanstack/react-query";
import { useRuntimeSnapshot } from "../../app/useRuntimeSnapshot";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import type { ProfileRuntimeResponse } from "../../shared/api/types";
import { Button } from "../../shared/ui";
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
  const { filters, setFilter, clearFilters } = useEnvironmentFilters();
  const [layout, setLayout] = useEnvironmentLayout();
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [createOpen, setCreateOpen] = useState(false);
  const [groupsOpen, setGroupsOpen] = useState(false);
  const [moveMenuOpen, setMoveMenuOpen] = useState(false);

  const { data: profiles = [] } = useProfilesQuery(client);
  const { data: groups = [] } = useGroupsQuery(client);
  const { data: proxies = [] } = useProxiesQuery(client);
  const snapshot = useRuntimeSnapshot(client);

  const runtimeQueries = useQueries({
    queries: profiles.map((item) => ({
      queryKey: profileKeys.runtime(item.id),
      queryFn: () => client.profiles.getRuntime(item.id),
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
      switch (action) {
        case "open":
          navigate(`/session/${id}`);
          break;
        case "start":
          startMutation.mutate({ id, state: "running" });
          break;
        case "stop":
          stopMutation.mutate(id);
          break;
        case "edit":
          navigate(`/profiles/${id}/config`);
          break;
        case "duplicate":
          duplicateMutation.mutate({ id, includeBrowserState: false });
          break;
        case "delete":
          deleteMutation.mutate(id);
          break;
      }
    },
    [navigate, startMutation, stopMutation, duplicateMutation, deleteMutation],
  );

  const handleMove = (groupId: string | null) => {
    setMoveMenuOpen(false);
    void run("moveToGroup", { groupId });
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
      <div
        data-testid="env-running-count"
        className="font-ui text-label-sm text-on-surface-muted"
      >
        {snapshot.runningCount}
      </div>

      {visibleRows.length === 0 ? (
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
            onDelete={() => void run("delete")}
            pending={pending}
          />
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
    </div>
  );
}
