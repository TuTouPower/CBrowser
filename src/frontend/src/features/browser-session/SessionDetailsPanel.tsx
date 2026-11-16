import { useState, type JSX, type ReactNode } from "react";
import { useI18n } from "../../i18n";
import type {
  FontSetInfo,
  GroupResponse,
  ProfileResponse,
  ProfileRuntimeResponse,
  ProxyResponse,
} from "../../shared/api/types";
import { Banner, Button, MonoValue } from "../../shared/ui";
import { formatFontSetDisplayName } from "../settings/SettingsPage";
import { formatPlatformLabel } from "../profiles/EnvironmentTable";
import { SESS_COPY_VALUE, SESS_DETAILS_PANEL, sessId } from "./session_keys";
import { transportStateLabelKey } from "./transport_state";

export interface SessionDetailsPanelProps {
  profile: ProfileResponse;
  runtime: ProfileRuntimeResponse | null;
  groups: GroupResponse[];
  proxies: ProxyResponse[];
  fontSets: FontSetInfo[];
  open: boolean;
}

function display(value: unknown): string {
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

interface ValueRowProps {
  label: string;
  value: string;
  copyKey: string;
  mono?: boolean;
  onCopy: (key: string, value: string) => void;
  copied: boolean;
  copyLabel: string;
  copiedLabel: string;
}

function ValueRow({
  label,
  value,
  copyKey,
  mono = false,
  onCopy,
  copied,
  copyLabel,
  copiedLabel,
}: ValueRowProps) {
  return (
    <div className="flex items-start justify-between gap-sm">
      <dt className="font-ui text-label-sm text-on-surface-muted">{label}</dt>
      <dd className="flex items-center gap-sm">
        {mono ? (
          <MonoValue>{value}</MonoValue>
        ) : (
          <span className="font-ui text-body-sm text-on-surface">{value}</span>
        )}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          data-testid={SESS_COPY_VALUE}
          data-copy-key={copyKey}
          aria-label={copyLabel}
          onClick={() => onCopy(copyKey, value)}
        >
          {copyLabel}
        </Button>
        {copied && (
          <span
            aria-live="polite"
            className="font-ui text-label-sm text-on-surface-muted"
          >
            {copiedLabel}
          </span>
        )}
      </dd>
    </div>
  );
}

function Section({
  title,
  id,
  rows,
  extra,
}: {
  title: string;
  id: string;
  rows: ReactNode;
  extra?: ReactNode;
}) {
  return (
    <section
      data-testid={sessId("details-section", id)}
      className="flex flex-col gap-sm"
    >
      <h3 className="font-ui text-title-sm text-on-surface">{title}</h3>
      <dl className="flex flex-col gap-sm">{rows}</dl>
      {extra}
    </section>
  );
}

export function SessionDetailsPanel(props: SessionDetailsPanelProps): JSX.Element {
  const { t } = useI18n();
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const { profile, runtime, groups, proxies, fontSets, open } = props;

  const copyValue = (key: string, value: string) => {
    const clipboard = navigator.clipboard;
    if (!clipboard?.writeText) return;
    void clipboard.writeText(value).then(
      () => setCopiedKey(key),
      () => setCopiedKey(null),
    );
  };

  const rowProps = {
    onCopy: copyValue,
    copyLabel: t("sessCopy"),
    copiedLabel: t("sessCopied"),
  };

  const renderRow = (
    label: string,
    value: string,
    copyKey: string,
    mono = false,
  ) => (
    <ValueRow
      key={copyKey}
      label={label}
      value={value}
      copyKey={copyKey}
      mono={mono}
      copied={copiedKey === copyKey}
      {...rowProps}
    />
  );

  const group = groups.find((item) => item.id === profile.group_id);
  const proxy = proxies.find((item) => item.id === profile.proxy_id);
  const fontSetId = runtime?.font_set_id ?? profile.font_set_id ?? null;
  const fontSet = fontSets.find((item) => item.set_id === fontSetId);
  const missingFonts = runtime?.missing_fonts ?? [];
  const transport = runtime?.transport ?? null;
  const configPending =
    runtime !== null && runtime.config_version !== profile.current_config_version;
  const proxySummary = proxy ? proxy.name : t("envDirect");
  const proxyEndpoint = proxy ? `${proxy.host}:${proxy.port}` : "-";
  const proxyRegion = (() => {
    if (!proxy) return "-";
    if (proxy.observation_status === "pending") return t("proxyCountryProbing");
    if (proxy.observation_status === "failed") {
      return proxy.observation_error_code ?? t("proxyProbeFailed");
    }
    if (proxy.observation_status === "ok") {
      const place = [proxy.country_name ?? proxy.country_code, proxy.city]
        .filter(Boolean)
        .join(" · ");
      const latency =
        proxy.latency_ms != null ? ` · ${proxy.latency_ms}ms` : "";
      return `${place || t("proxyCountryUnknown")}${latency}`;
    }
    return t("proxyCountryUnknown");
  })();
  const platformLabel = formatPlatformLabel(profile.fingerprint_platform, t);
  const fontSetLabel = fontSet
    ? formatFontSetDisplayName(fontSet, t)
    : t("formFontSetNone");
  const integrity = fontSet
    ? fontSet.integrity.ok
      ? t("fontSetIntegrityOk")
      : t("fontSetIntegrityBad")
    : "-";

  if (!open) return <></>;

  return (
    <aside
      data-testid={SESS_DETAILS_PANEL}
      aria-label={t("sessDetails")}
      className="flex h-full w-details flex-col gap-md border-l border-outline bg-surface p-md"
    >
      <div className="flex flex-col gap-lg overflow-y-auto">
        <Section
          title={t("navEnvironments")}
          id="environment"
          rows={[
            renderRow(t("envColName"), display(profile.name), "profile.name"),
            renderRow(
              t("sessGroup"),
              display(group?.name ?? t("sessUngrouped")),
              "group.name",
            ),
            renderRow(
              t("envSortCreated"),
              display(profile.created_at),
              "profile.created_at",
              true,
            ),
          ]}
        />

        <Section
          title={t("envColNetwork")}
          id="network"
          rows={[
            renderRow(t("envColNetwork"), proxySummary, "proxy.summary"),
            renderRow(t("proxyColAddress"), proxyEndpoint, "proxy.endpoint", true),
            renderRow(t("proxyColRegion"), proxyRegion, "proxy.region"),
            renderRow(
              t("sessionDiagRemoteEndpoint"),
              display(transport?.gateway_endpoint),
              "transport.gateway_endpoint",
              true,
            ),
          ]}
        />

        <Section
          title={t("envColFingerprint")}
          id="fingerprint"
          rows={[
            renderRow(
              t("formPlatform"),
              platformLabel,
              "profile.fingerprint_platform",
            ),
            renderRow(t("formFontSet"), fontSetLabel, "font_set_id"),
            renderRow(t("fontSetIntegrity"), integrity, "font_set_integrity"),
          ]}
          extra={
            missingFonts.length > 0 ? (
              <Banner
                tone="warning"
                testId={sessId("details", "missing-fonts")}
              >
                <div className="flex items-center justify-between gap-sm">
                  <span className="font-ui text-body-sm">
                    {t("fontSetDetectionMissing")}: {missingFonts.join(", ")}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    data-testid={SESS_COPY_VALUE}
                    onClick={() =>
                      copyValue("missing_fonts", missingFonts.join(", "))
                    }
                  >
                    {copiedKey === "missing_fonts"
                      ? t("sessCopied")
                      : t("sessCopy")}
                  </Button>
                </div>
              </Banner>
            ) : undefined
          }
        />

        <Section
          title={t("automationRuntimeState")}
          id="runtime"
          rows={[
            renderRow(
              t("appVersion"),
              display(runtime?.browser_product),
              "browser_product",
              true,
            ),
            renderRow(
              "User-Agent",
              display(runtime?.browser_user_agent),
              "browser_user_agent",
              true,
            ),
            renderRow(
              t("sessTransport"),
              t(transportStateLabelKey(transport?.transport_state)),
              "transport_state",
            ),
            renderRow(
              t("envColLastActive"),
              display(runtime?.last_started_at),
              "last_started_at",
              true,
            ),
          ]}
          extra={
            configPending ? (
              <p className="rounded-md border border-warning bg-warning-soft px-md py-sm font-ui text-label-sm text-on-surface">
                {t("sessApplyPending")}
              </p>
            ) : undefined
          }
        />
      </div>
    </aside>
  );
}
