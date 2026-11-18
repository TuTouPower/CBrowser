import { FolderCog, LayoutGrid, List, Plus } from "lucide-react";
import { useI18n } from "../../i18n";
import {
  Button,
  SearchField,
  SearchableSelect,
  Select,
  type SelectOption,
} from "../../shared/ui";
import {
  isFiltered,
  type EnvironmentFilters,
  type EnvironmentPlatformFilter,
  type EnvironmentSort,
  type EnvironmentStatusFilter,
  type SetEnvironmentFilter,
} from "./useEnvironmentFilters";
import type { EnvironmentLayout } from "./useEnvironmentLayout";

export interface EnvironmentListToolbarProps {
  filters: EnvironmentFilters;
  setFilter: SetEnvironmentFilter;
  layout: EnvironmentLayout;
  setLayout: (layout: EnvironmentLayout) => void;
  onNew: () => void;
  onManageGroups: () => void;
  /** t076 review f006: filter options come from the bounded candidate
   * endpoints — only id and name are needed here. */
  groups: Array<{ id: string; name: string }>;
  proxies: Array<{ id: string; name: string }>;
  onClearFilters: () => void;
}

const MANAGE_GROUPS_VALUE = "__manage__";

export function EnvironmentListToolbar({
  filters,
  setFilter,
  layout,
  setLayout,
  onNew,
  onManageGroups,
  groups,
  proxies,
  onClearFilters,
}: EnvironmentListToolbarProps) {
  const { t } = useI18n();

  const statusOptions: SelectOption[] = [
    { value: "all", label: t("envFilterAll") },
    { value: "running", label: t("statusRunning") },
    { value: "stopped", label: t("statusStopped") },
    { value: "error", label: t("statusError") },
  ];
  const groupOptions: SelectOption[] = [
    { value: "all", label: t("envFilterAllGroups") },
    { value: "ungrouped", label: t("envFilterUngrouped") },
    ...groups.map((item) => ({ value: item.id, label: item.name })),
    { value: MANAGE_GROUPS_VALUE, label: t("envManageGroups") },
  ];
  const platformOptions: SelectOption[] = [
    { value: "all", label: t("envFilterAllPlatforms") },
    { value: "windows", label: t("formPlatformWindows") },
    { value: "macos", label: t("formPlatformMacos") },
  ];
  const proxyOptions: SelectOption[] = [
    { value: "all", label: t("envFilterProxy") },
    { value: "direct", label: t("envDirect") },
    ...proxies.map((item) => ({ value: item.id, label: item.name })),
  ];
  const sortOptions: SelectOption[] = [
    { value: "manual", label: t("envSortManual") },
    { value: "name", label: t("envSortName") },
    { value: "recent", label: t("envSortRecent") },
    { value: "created", label: t("envSortCreated") },
  ];

  return (
    <div className="flex flex-wrap items-center justify-between gap-sm">
      <div className="flex flex-wrap items-center gap-sm">
        <SearchField
          data-testid="env-search"
          label={t("envSearch")}
          placeholder={t("envSearch")}
          value={filters.q}
          onChange={(event) => setFilter("q", event.target.value)}
          containerClassName="w-(--component-search-field-width)"
        />
        <Select
          ariaLabel={t("envFilterAll")}
          value={filters.status}
          onValueChange={(value) =>
            setFilter("status", value as EnvironmentStatusFilter)
          }
          options={statusOptions}
        />
        <SearchableSelect
          ariaLabel={t("envFilterAllGroups")}
          value={filters.group}
          onValueChange={(value) => {
            if (value === MANAGE_GROUPS_VALUE) onManageGroups();
            else setFilter("group", value);
          }}
          options={groupOptions}
          searchPlaceholder={t("searchGroups")}
          noResultsLabel={t("noMatchingGroups")}
        />
        <div data-testid="env-platform-filter">
          <Select
            ariaLabel={t("envFilterPlatform")}
            value={filters.platform ?? "all"}
            onValueChange={(value) =>
              setFilter("platform", value as EnvironmentPlatformFilter)
            }
            options={platformOptions}
          />
        </div>
        <SearchableSelect
          ariaLabel={t("envFilterProxy")}
          value={filters.proxy}
          onValueChange={(value) => setFilter("proxy", value)}
          options={proxyOptions}
          searchPlaceholder={t("proxySearch")}
          noResultsLabel={t("noMatchingProxies")}
        />
        <Select
          ariaLabel={t("envSortManual")}
          value={filters.sort}
          onValueChange={(value) =>
            setFilter("sort", value as EnvironmentSort)
          }
          options={sortOptions}
        />
        {isFiltered(filters) && (
          <Button
            data-testid="env-clear-filters"
            size="sm"
            onClick={onClearFilters}
          >
            {t("envClearFilters")}
          </Button>
        )}
      </div>

      <div className="ml-auto flex items-center gap-sm">
        <Button
          data-testid="env-manage-groups"
          variant="secondary"
          onClick={onManageGroups}
        >
          <FolderCog aria-hidden="true" className="size-(--component-icon-md-size)" />
          <span>{t("envManageGroups")}</span>
        </Button>

        <div className="flex items-center gap-2xs rounded-md border border-outline bg-surface p-2xs">
          <button
            type="button"
            data-testid="env-layout-list"
            aria-label={t("envLayoutList")}
            title={t("envLayoutList")}
            onClick={() => setLayout("list")}
            className={`inline-flex size-(--container-control-sm) items-center justify-center rounded-sm transition-colors ${
              layout === "list"
                ? "bg-accent text-on-accent"
                : "text-on-surface-muted hover:bg-surface-hover hover:text-on-surface"
            }`}
          >
            <List aria-hidden="true" className="size-(--component-icon-md-size)" />
          </button>
          <button
            type="button"
            data-testid="env-layout-card"
            aria-label={t("envLayoutCard")}
            title={t("envLayoutCard")}
            onClick={() => setLayout("card")}
            className={`inline-flex size-(--container-control-sm) items-center justify-center rounded-sm transition-colors ${
              layout === "card"
                ? "bg-accent text-on-accent"
                : "text-on-surface-muted hover:bg-surface-hover hover:text-on-surface"
            }`}
          >
            <LayoutGrid aria-hidden="true" className="size-(--component-icon-md-size)" />
          </button>
        </div>

        <Button
          data-testid="env-new"
          variant="primary"
          onClick={onNew}
        >
          <Plus aria-hidden="true" className="size-(--component-icon-md-size)" />
          <span>{t("envNew")}</span>
        </Button>
      </div>
    </div>
  );
}
