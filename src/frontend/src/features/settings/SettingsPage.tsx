import { useEffect, useState, type ReactNode } from "react";
import {
  Download,
  Globe,
  Network,
  Palette,
  Settings as SettingsIcon,
  ShieldCheck,
  Type,
} from "lucide-react";
import { useI18n } from "../../i18n";
import { useTheme, type ThemePreference } from "../../theme";
import { useApiClient } from "../../shared/api/client_context";
import { Banner, Button, Select, StatusBadge } from "../../shared/ui";

interface NetworkAccessConfig {
  lan_access_enabled: boolean;
  lan_advertised_ip?: string | null;
  https_port?: number;
}

interface AppliedNetworkAccessVersion {
  version: number;
  config: NetworkAccessConfig;
  applied_at: string;
  caddyfile_sha256: string;
  origin_whitelist: string[];
}

interface NetworkApplyOperation {
  operation_id: string;
  target_version: number;
  phase: string;
  error_reason?: string | null;
  new_entry_url?: string | null;
  created_at: string;
  updated_at: string;
}

interface NetworkSettingsResponse {
  pending_config: NetworkAccessConfig;
  applied_version: AppliedNetworkAccessVersion;
  active_operation?: NetworkApplyOperation | null;
}

interface FontSetIntegrity {
  ok: boolean;
  problems?: string[];
}

interface FontSetInfo {
  platform: string;
  set_id: string;
  source?: string | null;
  source_version?: string | null;
  integrity: FontSetIntegrity;
  file_count: number;
  used_by_count: number;
}

function Section({
  icon,
  title,
  description,
  children,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-outline bg-surface p-lg">
      <div className="mb-md flex items-center gap-md">
        <span className="text-on-surface-muted">{icon}</span>
        <div>
          <h2 className="font-ui text-title-sm text-on-surface">{title}</h2>
          <p className="font-ui text-body-sm text-on-surface-muted">{description}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

export function SettingsPage() {
  const { locale, setLocale, t } = useI18n();
  const { preference, setPreference } = useTheme();
  const client = useApiClient();
  const [healthStatus, setHealthStatus] = useState<
    "checking" | "healthy" | "error"
  >("checking");
  const [fontSets, setFontSets] = useState<FontSetInfo[] | null>(null);
  const [fontSetsError, setFontSetsError] = useState(false);

  // Network access state (t042)
  const [netSettings, setNetSettings] = useState<NetworkSettingsResponse | null>(null);
  const [netError, setNetError] = useState<string | null>(null);
  const [lanEnabled, setLanEnabled] = useState(false);
  const [lanIp, setLanIp] = useState("");
  const [httpsPort, setHttpsPort] = useState(56661);
  const [savingNet, setSavingNet] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [showApplyModal, setShowApplyModal] = useState(false);
  const [adminPassword, setAdminPassword] = useState("");
  const [applyState, setApplyState] = useState<"idle" | "applying" | "success" | "error">("idle");
  const [applyErrorMsg, setApplyErrorMsg] = useState<string | null>(null);
  const [disconnectNotice, setDisconnectNotice] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    client
      .request<NetworkSettingsResponse>("/api/v1/network/settings")
      .then((res) => {
        if (active) {
          setNetSettings(res);
          setLanEnabled(res.pending_config.lan_access_enabled);
          setLanIp(res.pending_config.lan_advertised_ip ?? "");
          setHttpsPort(res.pending_config.https_port ?? 56661);
        }
      })
      .catch((err) => {
        if (active) setNetError(err?.message ?? "Failed to load network settings");
      });
    return () => {
      active = false;
    };
  }, [client]);

  const handleSaveNetwork = async () => {
    setSavingNet(true);
    setSaveSuccess(false);
    setNetError(null);
    try {
      await client.request("/api/v1/network/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lan_access_enabled: lanEnabled,
          lan_advertised_ip: lanEnabled ? lanIp.trim() : null,
          https_port: Number(httpsPort) || 56661,
        }),
      });
      setSaveSuccess(true);
      const updated = await client.request<NetworkSettingsResponse>("/api/v1/network/settings");
      setNetSettings(updated);
    } catch (e: any) {
      setNetError(e?.message ?? "Failed to save network configuration");
    } finally {
      setSavingNet(false);
    }
  };

  const handleOpenApply = async () => {
    setNetError(null);
    setApplyErrorMsg(null);
    try {
      const check = await client.request<{ will_disconnect: boolean; new_entry_url: string }>(
        "/api/v1/network/check-disconnect"
      );
      if (check.will_disconnect) {
        setDisconnectNotice(check.new_entry_url);
      } else {
        setDisconnectNotice(null);
      }
    } catch {
      setDisconnectNotice(null);
    }
    setShowApplyModal(true);
  };

  const handleConfirmApply = async () => {
    setApplyState("applying");
    setApplyErrorMsg(null);
    try {
      const op = await client.request<NetworkApplyOperation>("/api/v1/network/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ admin_password: adminPassword }),
      });
      setAdminPassword("");
      setShowApplyModal(false);

      // Poll operation until finished
      const pollTimer = setInterval(async () => {
        try {
          const cur = await client.request<NetworkApplyOperation>(
            `/api/v1/network/operations/${op.operation_id}`
          );
          if (cur.phase === "completed") {
            clearInterval(pollTimer);
            setApplyState("success");
            const refreshed = await client.request<NetworkSettingsResponse>("/api/v1/network/settings");
            setNetSettings(refreshed);
          } else if (cur.phase === "failed") {
            clearInterval(pollTimer);
            setApplyState("error");
            setApplyErrorMsg(cur.error_reason ?? "Application failed");
          }
        } catch {
          // Keep polling or network changing
        }
      }, 1000);
    } catch (e: any) {
      setApplyState("error");
      setApplyErrorMsg(e?.message ?? "Failed to initiate apply operation");
    }
  };

  useEffect(() => {
    let active = true;
    client.health
      .check()
      .then(() => {
        if (active) setHealthStatus("healthy");
      })
      .catch(() => {
        if (active) setHealthStatus("error");
      });
    return () => {
      active = false;
    };
  }, [client]);

  useEffect(() => {
    let active = true;
    client
      .request<FontSetInfo[]>("/api/v1/font-sets")
      .then((sets) => {
        if (active) setFontSets(sets);
      })
      .catch(() => {
        if (active) setFontSetsError(true);
      });
    return () => {
      active = false;
    };
  }, [client]);

  const themeOptions = [
    { value: "system", label: t("themeSystem") },
    { value: "light", label: t("themeLight") },
    { value: "dark", label: t("themeDark") },
  ];

  return (
    <div data-testid="settings-page" className="mx-auto max-w-3xl">
      <div className="mb-lg flex items-center gap-md">
        <SettingsIcon aria-hidden="true" className="h-6 w-6 text-on-surface-muted" />
        <h1 className="font-ui text-headline-lg text-on-surface">{t("settings")}</h1>
      </div>

      <div className="flex flex-col gap-lg">
        <Section
          icon={<Palette aria-hidden="true" className="h-5 w-5" />}
          title={t("appearance")}
          description={t("theme")}
        >
          <Select
            ariaLabel={t("theme")}
            value={preference}
            onValueChange={(value) => setPreference(value as ThemePreference)}
            options={themeOptions}
          />
        </Section>

        <Section
          icon={<Globe aria-hidden="true" className="h-5 w-5" />}
          title={t("language")}
          description={t("switchLanguage")}
        >
          <div className="flex gap-sm">
            <Button
              variant={locale === "en" ? "primary" : "secondary"}
              onClick={() => setLocale("en")}
            >
              {t("languageEn")}
            </Button>
            <Button
              variant={locale === "zh" ? "primary" : "secondary"}
              onClick={() => setLocale("zh")}
            >
              {t("languageZh")}
            </Button>
          </div>
        </Section>

        <Section
          icon={<ShieldCheck aria-hidden="true" className="h-5 w-5" />}
          title={t("controlApiStatusTitle")}
          description={t("controlApiStatusHint")}
        >
          <StatusBadge
            tone={
              healthStatus === "healthy"
                ? "running"
                : healthStatus === "error"
                  ? "error"
                  : "transition"
            }
            label={
              healthStatus === "healthy"
                ? t("healthHealthy")
                : healthStatus === "error"
                  ? t("healthUnreachable")
                  : t("healthChecking")
            }
          />
        </Section>

        {/* Network Access Section (t042) */}
        <Section
          icon={<Network aria-hidden="true" className="h-5 w-5" />}
          title={t("networkAccess")}
          description={t("networkAccessDesc")}
        >
          <div className="flex flex-col gap-md">
            {netError && (
              <Banner tone="danger" testId="network-settings-error">
                {netError}
              </Banner>
            )}
            {saveSuccess && (
              <Banner testId="network-save-success">
                {t("savedSuccess")}
              </Banner>
            )}
            {applyState === "success" && (
              <Banner testId="network-apply-success">
                {t("applySuccess")}
              </Banner>
            )}
            {applyState === "error" && applyErrorMsg && (
              <Banner tone="danger" testId="network-apply-error">
                {t("applyFailed", { reason: applyErrorMsg })}
              </Banner>
            )}

            {/* Current Applied Status vs Pending */}
            <div className="flex flex-wrap items-center justify-between gap-sm rounded-md border border-outline bg-surface-subtle p-md font-ui text-body-sm">
              <div className="flex flex-col gap-xs">
                <span className="font-ui text-label-md text-on-surface-muted">
                  {t("appliedStatus")}
                </span>
                <span className="font-mono text-mono-md text-on-surface">
                  {netSettings?.applied_version?.config?.lan_access_enabled
                    ? t("appliedLan", { ip: netSettings.applied_version.config.lan_advertised_ip ?? "" })
                    : t("appliedLocal")}
                </span>
              </div>
              <div className="flex flex-col gap-xs">
                <span className="font-ui text-label-md text-on-surface-muted">
                  {t("pendingChanges")}
                </span>
                <span className="font-mono text-mono-md text-on-surface">
                  {netSettings?.pending_config?.lan_access_enabled
                    ? `LAN: ${netSettings.pending_config.lan_advertised_ip ?? "—"}`
                    : "127.0.0.1 (Local)"}
                </span>
              </div>
            </div>

            {/* Toggle and IP Input */}
            <div className="flex flex-col gap-sm">
              <label className="flex items-center gap-sm font-ui text-body-md text-on-surface">
                <input
                  type="checkbox"
                  data-testid="lan-access-toggle"
                  checked={lanEnabled}
                  onChange={(e) => setLanEnabled(e.target.checked)}
                  className="h-4 w-4 rounded border-outline accent-accent"
                />
                {t("lanAccessToggle")}
              </label>

              {lanEnabled && (
                <div className="flex flex-col gap-xs pl-6">
                  <label htmlFor="lan-ip" className="font-ui text-label-sm text-on-surface-muted">
                    {t("lanAdvertisedIp")}
                  </label>
                  <input
                    id="lan-ip"
                    type="text"
                    data-testid="lan-ip-input"
                    value={lanIp}
                    onChange={(e) => setLanIp(e.target.value)}
                    placeholder={t("lanAdvertisedIpPlaceholder")}
                    className="max-w-hint rounded-md border border-outline bg-surface px-sm py-1 font-mono text-mono-md text-on-surface"
                  />
                </div>
              )}

              <div className="flex flex-col gap-xs pl-6">
                <label htmlFor="https-port" className="font-ui text-label-sm text-on-surface-muted">
                  {t("httpsPort")}
                </label>
                <input
                  id="https-port"
                  type="number"
                  data-testid="https-port-input"
                  value={httpsPort}
                  onChange={(e) => setHttpsPort(Number(e.target.value))}
                  min={1}
                  max={65535}
                  className="max-w-hint rounded-md border border-outline bg-surface px-sm py-1 font-mono text-mono-md text-on-surface"
                />
              </div>
            </div>

            {/* Save & Apply Buttons */}
            <div className="flex items-center gap-sm pt-sm">
              <Button
                variant="secondary"
                data-testid="save-network-btn"
                disabled={savingNet || applyState === "applying"}
                onClick={handleSaveNetwork}
              >
                {savingNet ? t("saving") : t("savePending")}
              </Button>
              <Button
                variant="primary"
                data-testid="apply-network-btn"
                disabled={savingNet || applyState === "applying"}
                onClick={handleOpenApply}
              >
                {applyState === "applying" ? t("applying") : t("applyChanges")}
              </Button>
            </div>

            {/* Root CA Certificate Download */}
            <div className="mt-md rounded-md border border-outline bg-surface-subtle p-md">
              <div className="flex items-center justify-between gap-sm">
                <div>
                  <h3 className="font-ui text-label-lg text-on-surface">
                    {t("downloadRootCa")}
                  </h3>
                  <p className="font-ui text-body-sm text-on-surface-muted">
                    {t("rootCaDesc")}
                  </p>
                </div>
                <a
                  href="/api/v1/network/root-ca"
                  download="cbrowser_root_ca.crt"
                  data-testid="download-root-ca-btn"
                  className="inline-flex items-center gap-xs rounded-md bg-accent px-md py-1.5 font-ui text-label-md text-on-accent"
                >
                  <Download className="h-4 w-4" />
                  {t("downloadRootCa")}
                </a>
              </div>
              <p className="mt-sm font-ui text-body-sm text-on-surface-muted">
                {t("rootCaInstructions")}
              </p>
            </div>
          </div>

          {/* Admin Password & Disconnect Modal */}
          {showApplyModal && (
            <div
              data-testid="apply-modal"
              className="fixed inset-0 z-50 flex items-center justify-center bg-overlay p-md"
            >
              <div className="w-full max-w-dialog rounded-lg border border-outline bg-surface p-lg shadow-lg">
                <h3 className="font-ui text-title-sm text-on-surface">
                  {t("confirmApply")}
                </h3>
                {disconnectNotice && (
                  <div className="my-md">
                    <Banner tone="warning" testId="disconnect-warning">
                      {t("disconnectWarningDesc", { url: disconnectNotice })}
                    </Banner>
                  </div>
                )}
                <div className="my-md flex flex-col gap-xs">
                  <label
                    htmlFor="admin-password-input"
                    className="font-ui text-label-sm text-on-surface-muted"
                  >
                    {t("adminPasswordPrompt")}
                  </label>
                  <input
                    id="admin-password-input"
                    type="password"
                    data-testid="admin-password-input"
                    value={adminPassword}
                    onChange={(e) => setAdminPassword(e.target.value)}
                    className="rounded-md border border-outline bg-surface px-sm py-1 font-ui text-body-md text-on-surface"
                  />
                </div>
                <div className="flex justify-end gap-sm">
                  <Button
                    variant="secondary"
                    data-testid="cancel-apply-btn"
                    onClick={() => {
                      setShowApplyModal(false);
                      setAdminPassword("");
                    }}
                  >
                    {t("cancel")}
                  </Button>
                  <Button
                    variant="primary"
                    data-testid="confirm-apply-btn"
                    disabled={!adminPassword.trim()}
                    onClick={handleConfirmApply}
                  >
                    {t("confirmApply")}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </Section>

        <Section
          icon={<Type aria-hidden="true" className="h-5 w-5" />}
          title={t("platformFontSets")}
          description={t("platformFontSets")}
        >
          {fontSetsError && (
            <Banner tone="danger" testId="font-sets-error">
              {t("fontSetsLoadFailed")}
            </Banner>
          )}
          {!fontSetsError && fontSets?.length === 0 && (
            <p className="font-ui text-body-sm text-on-surface-muted">
              {t("fontSetsEmpty")}
            </p>
          )}
          {fontSets && fontSets.length > 0 && (
            <div data-testid="font-sets" className="flex flex-col gap-sm">
              {fontSets.map((fontSet) => (
                <div
                  key={`${fontSet.platform}-${fontSet.set_id}`}
                  data-testid={`font-set-${fontSet.platform}-${fontSet.set_id}`}
                  className="rounded-md border border-outline bg-surface-subtle p-md"
                >
                  <div className="mb-sm flex items-center justify-between gap-sm">
                    <span className="font-mono text-mono-md text-on-surface">
                      {fontSet.platform}
                    </span>
                    {fontSet.integrity.ok ? (
                      <StatusBadge
                        tone="running"
                        label={t("fontSetIntegrityOk")}
                      />
                    ) : (
                      <span data-testid="font-set-integrity-bad">
                        <Banner tone="danger">
                          {t("fontSetIntegrityBad")}
                        </Banner>
                      </span>
                    )}
                  </div>
                  <dl className="grid grid-cols-2 gap-sm font-ui text-body-sm">
                    <div>
                      <dt className="text-on-surface-muted">{t("fontSetSource")}</dt>
                      <dd className="font-mono text-mono-md text-on-surface">
                        {fontSet.source ?? "—"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-on-surface-muted">{t("fontSetVersion")}</dt>
                      <dd className="font-mono text-mono-md text-on-surface">
                        {fontSet.source_version ?? "—"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-on-surface-muted">{t("fontSetFileCount")}</dt>
                      <dd className="font-mono text-mono-md text-on-surface">
                        {fontSet.file_count}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-on-surface-muted">{t("fontSetUsedBy")}</dt>
                      <dd className="font-mono text-mono-md text-on-surface">
                        {fontSet.used_by_count}
                      </dd>
                    </div>
                  </dl>
                  {!fontSet.integrity.ok && fontSet.integrity.problems?.length ? (
                    <ul
                      data-testid="font-set-problems"
                      className="mt-sm list-inside list-disc font-mono text-mono-md text-on-surface"
                    >
                      {fontSet.integrity.problems.map((problem) => (
                        <li key={problem}>{problem}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}
