import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router";
import type {
  ProfileResponse,
  ProfileRuntimeResponse,
  ProxyResponse,
} from "../../shared/api/types";

export type EnvironmentStatusFilter = "all" | "running" | "stopped" | "error";
export type EnvironmentSort = "manual" | "name" | "recent" | "created";

export interface EnvironmentFilters {
  q: string;
  status: EnvironmentStatusFilter;
  group: string;
  proxy: string;
  sort: EnvironmentSort;
}

export type SetEnvironmentFilter = <K extends keyof EnvironmentFilters>(
  key: K,
  value: EnvironmentFilters[K],
) => void;

const DEFAULTS: EnvironmentFilters = {
  q: "",
  status: "all",
  group: "all",
  proxy: "all",
  sort: "manual",
};

const STATUS_VALUES: EnvironmentStatusFilter[] = [
  "all",
  "running",
  "stopped",
  "error",
];
const SORT_VALUES: EnvironmentSort[] = ["manual", "name", "recent", "created"];

function isStatus(value: string | null): value is EnvironmentStatusFilter {
  return value !== null && STATUS_VALUES.includes(value as EnvironmentStatusFilter);
}

function isSort(value: string | null): value is EnvironmentSort {
  return value !== null && SORT_VALUES.includes(value as EnvironmentSort);
}

export function useEnvironmentFilters(): {
  filters: EnvironmentFilters;
  setFilter: SetEnvironmentFilter;
  clearFilters: () => void;
} {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters = useMemo<EnvironmentFilters>(() => {
    const status = searchParams.get("status");
    const sort = searchParams.get("sort");
    return {
      q: searchParams.get("q") ?? "",
      status: isStatus(status) ? status : "all",
      group: searchParams.get("group") ?? "all",
      proxy: searchParams.get("proxy") ?? "all",
      sort: isSort(sort) ? sort : "manual",
    };
  }, [searchParams]);

  const setFilter = useCallback<SetEnvironmentFilter>(
    (key, value) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          const fallback = DEFAULTS[key];
          if (value === "" || value === fallback) next.delete(key);
          else next.set(key, String(value));
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const clearFilters = useCallback(() => {
    setSearchParams(new URLSearchParams(), { replace: true });
  }, [setSearchParams]);

  return { filters, setFilter, clearFilters };
}

export function isFiltered(filters: EnvironmentFilters): boolean {
  return (
    filters.q !== "" ||
    filters.status !== "all" ||
    filters.group !== "all" ||
    filters.proxy !== "all"
  );
}

export interface FilterableEnvironmentRow {
  profile: ProfileResponse;
  runtime?: ProfileRuntimeResponse;
  proxy?: ProxyResponse;
}

function statusBucket(
  observed: string,
): "running" | "stopped" | "error" {
  if (observed === "error") return "error";
  if (observed === "running" || observed === "starting") return "running";
  return "stopped";
}

function lastActivity(row: FilterableEnvironmentRow): number {
  const started = Date.parse(row.runtime?.last_started_at ?? "") || 0;
  const stopped = Date.parse(row.runtime?.last_stopped_at ?? "") || 0;
  return Math.max(started, stopped);
}

export function filterEnvironmentRows<T extends FilterableEnvironmentRow>(
  rows: T[],
  filters: EnvironmentFilters,
): T[] {
  const query = filters.q.trim().toLowerCase();
  return rows.filter((row) => {
    const observed = row.runtime?.observed_state ?? "stopped";
    if (
      filters.status !== "all" &&
      statusBucket(observed) !== filters.status
    ) {
      return false;
    }
    if (filters.group === "ungrouped") {
      if (row.profile.group_id != null) return false;
    } else if (
      filters.group !== "all" &&
      row.profile.group_id !== filters.group
    ) {
      return false;
    }
    if (filters.proxy !== "all" && row.profile.proxy_id !== filters.proxy) {
      return false;
    }
    if (query) {
      const haystack = [
        row.profile.name,
        row.profile.notes ?? "",
        row.proxy?.name ?? "",
      ]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    return true;
  });
}

export function sortEnvironmentRows<T extends FilterableEnvironmentRow>(
  rows: T[],
  sort: EnvironmentSort,
): T[] {
  const copy = [...rows];
  switch (sort) {
    case "name":
      return copy.sort((a, b) =>
        a.profile.name.localeCompare(b.profile.name),
      );
    case "recent":
      return copy.sort((a, b) => lastActivity(b) - lastActivity(a));
    case "created":
      return copy.sort(
        (a, b) =>
          Date.parse(b.profile.created_at) - Date.parse(a.profile.created_at),
      );
    default:
      return copy.sort(
        (a, b) => a.profile.sort_order - b.profile.sort_order,
      );
  }
}
