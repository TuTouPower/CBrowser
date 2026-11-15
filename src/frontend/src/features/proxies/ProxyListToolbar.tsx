import { LayoutGrid, List, Plus, Zap } from "lucide-react";
import { useI18n } from "../../i18n";
import {
  Button,
  IconButton,
  SearchField,
  Select,
  type SelectOption,
} from "../../shared/ui";

export type ProxySchemeFilter = "all" | "http" | "https" | "socks5";
export type ProxyLayout = "list" | "card";

export interface ProxyListToolbarProps {
  query: string;
  onQueryChange: (value: string) => void;
  scheme: ProxySchemeFilter;
  onSchemeChange: (value: ProxySchemeFilter) => void;
  region?: string;
  onRegionChange?: (value: string) => void;
  regions?: Array<{ value: string; label: string }>;
  layout?: ProxyLayout;
  onLayoutChange?: (layout: ProxyLayout) => void;
  onProbeAll?: () => void;
  probingAll?: boolean;
  onAdd: () => void;
}

export function ProxyListToolbar({
  query,
  onQueryChange,
  scheme,
  onSchemeChange,
  region = "all",
  onRegionChange,
  regions = [],
  layout = "list",
  onLayoutChange,
  onProbeAll,
  probingAll = false,
  onAdd,
}: ProxyListToolbarProps) {
  const { t } = useI18n();

  const schemeOptions: SelectOption[] = [
    { value: "all", label: t("proxyFilterAll") },
    { value: "http", label: "HTTP" },
    { value: "https", label: "HTTPS" },
    { value: "socks5", label: "SOCKS5" },
  ];

  const regionOptions: SelectOption[] = [
    { value: "all", label: t("proxyFilterAllRegions") },
    ...regions,
  ];

  return (
    <div className="flex flex-wrap items-center justify-between gap-sm">
      <div className="flex flex-wrap items-center gap-sm">
        <SearchField
          data-testid="proxy-search"
          label={t("proxySearch")}
          placeholder={t("proxySearch")}
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
        />
        <div data-testid="proxy-scheme-filter">
          <Select
            ariaLabel={t("proxyFilterScheme")}
            value={scheme}
            onValueChange={(value) =>
              onSchemeChange(value as ProxySchemeFilter)
            }
            options={schemeOptions}
          />
        </div>
        {onRegionChange && (
          <div data-testid="proxy-region-filter">
            <Select
              ariaLabel={t("proxyFilterRegion")}
              value={region}
              onValueChange={onRegionChange}
              options={regionOptions}
            />
          </div>
        )}
      </div>

      <div className="ml-auto flex items-center gap-sm">
        {onProbeAll && (
          <IconButton
            data-testid="proxy-probe-all"
            label={t("proxyProbeAll")}
            disabled={probingAll}
            onClick={onProbeAll}
          >
            <Zap
              aria-hidden="true"
              className="size-(--component-icon-md-size)"
            />
          </IconButton>
        )}

        {onLayoutChange && (
          <div className="flex items-center gap-2xs rounded-md border border-outline bg-surface p-2xs">
            <button
              type="button"
              data-testid="proxy-layout-list"
              aria-label={t("envLayoutList")}
              title={t("envLayoutList")}
              onClick={() => onLayoutChange("list")}
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
              data-testid="proxy-layout-card"
              aria-label={t("envLayoutCard")}
              title={t("envLayoutCard")}
              onClick={() => onLayoutChange("card")}
              className={`inline-flex size-(--container-control-sm) items-center justify-center rounded-sm transition-colors ${
                layout === "card"
                  ? "bg-accent text-on-accent"
                  : "text-on-surface-muted hover:bg-surface-hover hover:text-on-surface"
              }`}
            >
              <LayoutGrid aria-hidden="true" className="size-(--component-icon-md-size)" />
            </button>
          </div>
        )}

        <Button data-testid="proxy-add" variant="primary" onClick={onAdd}>
          <Plus aria-hidden="true" className="size-(--component-icon-md-size)" />
          <span>{t("proxyAdd")}</span>
        </Button>
      </div>
    </div>
  );
}
