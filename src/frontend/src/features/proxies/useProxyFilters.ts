import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router";

export type ProxySchemeFilter = "all" | "http" | "https" | "socks5";

export interface ProxyFilters {
  q: string;
  scheme: ProxySchemeFilter;
  country: string;
  city: string;
}

export type SetProxyFilter = <K extends keyof ProxyFilters>(
  key: K,
  value: ProxyFilters[K],
) => void;

const DEFAULTS: ProxyFilters = {
  q: "",
  scheme: "all",
  country: "all",
  city: "all",
};

const SCHEME_VALUES: ProxySchemeFilter[] = ["all", "http", "https", "socks5"];

function isScheme(value: string | null): value is ProxySchemeFilter {
  return value !== null && SCHEME_VALUES.includes(value as ProxySchemeFilter);
}

// URL SearchParams keep q / scheme / country / city across reloads (t074 AC-003).
// Linked filters (country change also resets city) must be committed in a
// single setSearchParams call: two calls in one tick both read the same
// stale location.search and the last one silently drops the first update.
export function useProxyFilters(): {
  filters: ProxyFilters;
  setFilter: SetProxyFilter;
  setFilters: (patch: Partial<ProxyFilters>) => void;
  clearFilters: () => void;
} {
  const [searchParams, setSearchParams] = useSearchParams();

  const filters = useMemo<ProxyFilters>(() => {
    const scheme = searchParams.get("scheme");
    return {
      q: searchParams.get("q") ?? "",
      scheme: isScheme(scheme) ? scheme : "all",
      country: searchParams.get("country") ?? "all",
      city: searchParams.get("city") ?? "all",
    };
  }, [searchParams]);

  const setFilters = useCallback(
    (patch: Partial<ProxyFilters>) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          for (const key of Object.keys(patch) as (keyof ProxyFilters)[]) {
            const value = patch[key];
            if (value === undefined) continue;
            const fallback = DEFAULTS[key];
            if (value === "" || value === fallback) next.delete(key);
            else next.set(key, String(value));
          }
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const setFilter = useCallback<SetProxyFilter>(
    (key, value) => {
      const patch: Partial<ProxyFilters> = {};
      patch[key] = value;
      setFilters(patch);
    },
    [setFilters],
  );

  const clearFilters = useCallback(() => {
    setSearchParams(new URLSearchParams(), { replace: true });
  }, [setSearchParams]);

  return { filters, setFilter, setFilters, clearFilters };
}
