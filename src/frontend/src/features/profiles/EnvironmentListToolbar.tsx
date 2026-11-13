import { useI18n } from "../../i18n";
import type { GroupResponse, ProxyResponse } from "../../shared/api/types";
import {
  Button,
  SearchField,
  Select,
  type SelectOption,
} from "../../shared/ui";
import {
  isFiltered,
  type EnvironmentFilters,
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
  groups: GroupResponse[];
  proxies: ProxyResponse[];
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
    { value: "running", label: t("envFilterRunning") },
    { value: "stopped", label: t("envFilterStopped") },
    { value: "error", label: t("envFilterError") },
  ];
  const groupOptions: SelectOption[] = [
    { value: "all", label: t("envFilterAllGroups") },
    { value: "ungrouped", label: t("envFilterUngrouped") },
    ...groups.map((item) => ({ value: item.id, label: item.name })),
    { value: MANAGE_GROUPS_VALUE, label: t("envManageGroups") },
  ];
  const proxyOptions: SelectOption[] = [
    { value: "all", label: t("envFilterProxy") },
    ...proxies.map((item) => ({ value: item.id, label: item.name })),
  ];
  const sortOptions: SelectOption[] = [
    { value: "manual", label: t("envSortManual") },
    { value: "name", label: t("envSortName") },
    { value: "recent", label: t("envSortRecent") },
    { value: "created", label: t("envSortCreated") },
  ];

  return (
    <div className="flex flex-col gap-md">
      <div className="flex flex-wrap items-center justify-between gap-md">
        <h1
          data-testid="env-title"
          className="font-ui text-headline-md text-on-surface"
        >
          {t("envTitle")}
        </h1>
        <Button
          data-testid="env-new"
          variant="primary"
          onClick={onNew}
        >
          {t("envNew")}
        </Button>
      </div>
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
        <Select
          ariaLabel={t("envFilterAllGroups")}
          value={filters.group}
          onValueChange={(value) => {
            if (value === MANAGE_GROUPS_VALUE) onManageGroups();
            else setFilter("group", value);
          }}
          options={groupOptions}
        />
        <Select
          ariaLabel={t("envFilterProxy")}
          value={filters.proxy}
          onValueChange={(value) => setFilter("proxy", value)}
          options={proxyOptions}
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
        <div className="ml-auto flex items-center gap-xs">
          <Button
            data-testid="env-layout-list"
            size="sm"
            variant={layout === "list" ? "primary" : "secondary"}
            onClick={() => setLayout("list")}
          >
            {t("envLayoutList")}
          </Button>
          <Button
            data-testid="env-layout-card"
            size="sm"
            variant={layout === "card" ? "primary" : "secondary"}
            onClick={() => setLayout("card")}
          >
            {t("envLayoutCard")}
          </Button>
        </div>
      </div>
    </div>
  );
}
