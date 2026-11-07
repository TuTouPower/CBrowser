import { useI18n } from "../../i18n";
import {
  Button,
  SearchField,
  Select,
  type SelectOption,
} from "../../shared/ui";

export type ProxySchemeFilter = "all" | "http" | "https" | "socks5";

export interface ProxyListToolbarProps {
  query: string;
  onQueryChange: (value: string) => void;
  scheme: ProxySchemeFilter;
  onSchemeChange: (value: ProxySchemeFilter) => void;
  onAdd: () => void;
}

export function ProxyListToolbar({
  query,
  onQueryChange,
  scheme,
  onSchemeChange,
  onAdd,
}: ProxyListToolbarProps) {
  const { t } = useI18n();

  const schemeOptions: SelectOption[] = [
    { value: "all", label: t("proxyFilterAll") },
    { value: "http", label: "HTTP" },
    { value: "https", label: "HTTPS" },
    { value: "socks5", label: "SOCKS5" },
  ];

  return (
    <div className="flex flex-col gap-md">
      <div className="flex flex-wrap items-center justify-between gap-md">
        <h1
          data-testid="proxy-title"
          className="font-ui text-headline-md text-on-surface"
        >
          {t("proxyTitle")}
        </h1>
        <Button data-testid="proxy-add" variant="primary" onClick={onAdd}>
          {t("proxyAdd")}
        </Button>
      </div>
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
      </div>
    </div>
  );
}
