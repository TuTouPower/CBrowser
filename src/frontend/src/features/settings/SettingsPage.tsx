import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
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
import type {
  NetworkAccessConfig,
  NetworkApplyOperation,
  NetworkApplyRequest,
} from "../../shared/api/types";
import { Banner, Button, Select, StatusBadge } from "../../shared/ui";
import { useFontSetsQuery } from "../profiles/useProfilesQuery";
import {
  isTerminalOperation,
  useNetworkOperationPolling,
} from "./useNetworkOperationPolling";
import { networkKeys, useNetworkSettingsQuery } from "./useNetworkQueries";

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
  const queryClient = useQueryClient();
  const settingsQuery = useNetworkSettingsQuery(client);
  const fontSetsQuery = useFontSetsQuery(client);
  const netSettings = settingsQuery.data ?? null;
  const fontSets = fontSetsQuery.data?.items ?? null;
  const fontSetsError = fontSetsQuery.isError;
  const formSeededRef = useRef(false);
  const formDirtyRef = useRef(false);
  const [healthStatus, setHealthStatus] = useState<
    "checking" | "healthy" | "error"
  >("checking");
  const [actionError, setActionError] = useState<string | null>(null);
  const [lanEnabled, setLanEnabled] = useState(false);
  const [lanIp, setLanIp] = useState("");
  const [httpsPort, setHttpsPort] = useState(56661);
  const [savingNet, setSavingNet] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [showApplyModal, setShowApplyModal] = useState(false);
  const [adminPassword, setAdminPassword] = useState("");
  const [applyState, setApplyState] = useState<
    "idle" | "applying" | "success" | "error" | "disconnected"
  >("idle");
  const [applyErrorMsg, setApplyErrorMsg] = useState<string | null>(null);
  const [disconnectNotice, setDisconnectNotice] = useState<string | null>(null);
  const [trackedOperation, setTrackedOperation] = useState<NetworkApplyOperation | null>(null);
  const [entryUrl, setEntryUrl] = useState<string | null>(null);
  const [lastPhase, setLastPhase] = useState<string | null>(null);

  const netError =
    actionError ??
    (settingsQuery.error ? settingsQuery.error.message : null);
  const activeOperation = settingsQuery.data?.active_operation ?? null;

  useEffect(() => {
    const data = settingsQuery.data;
    if (!data || formSeededRef.current) return;
    formSeededRef.current = true;
    if (formDirtyRef.current) return;
    setLanEnabled(data.pending_config.lan_access_enabled);
    setLanIp(data.pending_config.lan_advertised_ip ?? "");
    setHttpsPort(data.pending_config.https_port ?? 56661);
  }, [settingsQuery.data]);

  useEffect(() => {
    if (applyState !== "idle") return;
    if (!activeOperation || isTerminalOperation(activeOperation)) return;
    setTrackedOperation(activeOperation);
    setEntryUrl((prev) => activeOperation.new_entry_url ?? prev);
    setApplyState("applying");
  }, [activeOperation, applyState]);

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

  const applying = applyState === "applying";
  const handleSaveNetwork = async () => {
    setSavingNet(true);
    setSaveSuccess(false);
    setActionError(null);
    try {
      const rawPort = Number(httpsPort);
      if (!Number.isInteger(rawPort) || rawPort < 1 || rawPort > 65535) {
        // P2: 端口文案不再复用代理库 copy，用网络专属 key。
        setActionError(t("httpsPortInvalid"));
        return;
      }
      const trimmedIp = lanIp.trim();
      const config: NetworkAccessConfig = {
        lan_access_enabled: lanEnabled,
        // P2: LAN 空值（空串/空白）一律落 null，不发空串。
        lan_advertised_ip: lanEnabled && trimmedIp ? trimmedIp : null,
        https_port: rawPort,
      };
      await client.network.updateSettings(config);
      setSaveSuccess(true);
      queryClient.invalidateQueries({ queryKey: networkKeys.settings() });
    } catch (e: any) {
      setActionError(e?.message ?? "Failed to save network configuration");
    } finally {
      setSavingNet(false);
    }
  };

  const handleOpenApply = async () => {
    setActionError(null);
    setApplyErrorMsg(null);
    try {
      const check = await client.network.checkDisconnect();
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
      const body: NetworkApplyRequest = { admin_password: adminPassword };
      const op = await client.network.apply(body);
      setAdminPassword("");
      setShowApplyModal(false);
      setEntryUrl(op.new_entry_url ?? disconnectNotice);
      setLastPhase(null);
      setTrackedOperation(op);
    } catch (e: any) {
      setApplyState("error");
      setApplyErrorMsg(e?.message ?? "Failed to initiate apply operation");
    }
  };

  useNetworkOperationPolling(
    (id, signal) => client.network.getOperation(id, signal),
    trackedOperation,
    {
      onCompleted: (op) => {
        setApplyState("success");
        setEntryUrl((prev) => op.new_entry_url ?? prev);
        setTrackedOperation(null);
        queryClient.invalidateQueries({ queryKey: networkKeys.settings() });
      },
      onFailed: (op) => {
        setApplyState("error");
        setApplyErrorMsg(op.error_reason ?? "Application failed");
        setTrackedOperation(null);
      },
      onDeadline: (lastKnown) => {
        setApplyState("disconnected");
        setLastPhase(lastKnown.phase);
        setEntryUrl((prev) => lastKnown.new_entry_url ?? prev);
        setTrackedOperation(null);
      },
    },
  );

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
                <div className="flex flex-col gap-xs">
                  <span>{t("applySuccess")}</span>
                  {entryUrl && (
                    <a
                      data-testid="network-apply-entry-link"
                      href={entryUrl}
                      className="font-mono text-mono-md text-on-surface underline"
                    >
                      {entryUrl}
                    </a>
                  )}
                </div>
              </Banner>
            )}
            {applyState === "error" && applyErrorMsg && (
              <Banner tone="danger" testId="network-apply-error">
                {t("applyFailed", { reason: applyErrorMsg })}
              </Banner>
            )}
            {applyState === "disconnected" && (
              <Banner tone="warning" testId="network-apply-disconnected">
                <div className="flex flex-col gap-xs">
                  <span className="font-ui text-label-md text-on-surface">
                    {t("disconnectWarningTitle")}
                  </span>
                  {/* P2: 去掉与标题重复的 applyFailed(healthUnreachable) 行，
                      保留 lastPhase + 新地址描述 + 链接，避免重复提示。 */}
                  {lastPhase && (
                    <span
                      data-testid="network-last-phase"
                      className="font-mono text-mono-md text-on-surface"
                    >
                      {lastPhase}
                    </span>
                  )}
                  {entryUrl && (
                    <>
                      <span className="font-ui text-body-sm text-on-surface-muted">
                        {t("disconnectWarningDesc", { url: entryUrl })}
                      </span>
                      <a
                        data-testid="network-reconnect-link"
                        href={entryUrl}
                        className="font-mono text-mono-md text-on-surface underline"
                      >
                        {entryUrl}
                      </a>
                    </>
                  )}
                </div>
              </Banner>
            )}

            <div className="flex flex-wrap items-center justify-between gap-sm rounded-md border border-outline bg-surface-subtle p-md font-ui text-body-sm">
              <div className="flex flex-col gap-xs">
                <span className="font-ui text-label-md text-on-surface-muted">
                  {t("appliedStatus")}
                </span>
                <span className="font-mono text-mono-md text-on-surface">
                  {netSettings?.applied_version?.config?.lan_access_enabled
                    ? t("appliedLan", { ip: netSettings.applied_version.config.lan_advertised_ip ?? "—" })
                    : t("appliedLocal")}
                </span>
              </div>
              <div className="flex flex-col gap-xs">
                <span className="font-ui text-label-md text-on-surface-muted">
                  {t("pendingChanges")}
                </span>
                <span className="font-mono text-mono-md text-on-surface">
                  {netSettings?.pending_config?.lan_access_enabled
                    ? t("appliedLan", {
                        ip: netSettings.pending_config.lan_advertised_ip ?? "—",
                      })
                    : t("appliedLocal")}
                </span>
              </div>
            </div>

            <div className="flex flex-col gap-sm">
              <label className="flex items-center gap-sm font-ui text-body-md text-on-surface">
                <input
                  type="checkbox"
                  data-testid="lan-access-toggle"
                  checked={lanEnabled}
                  onChange={(e) => {
                    formDirtyRef.current = true;
                    setLanEnabled(e.target.checked);
                  }}
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
                    onChange={(e) => {
                      formDirtyRef.current = true;
                      setLanIp(e.target.value);
                    }}
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
                  onChange={(e) => {
                    formDirtyRef.current = true;
                    setHttpsPort(Number(e.target.value));
                  }}
                  min={1}
                  max={65535}
                  className="max-w-hint rounded-md border border-outline bg-surface px-sm py-1 font-mono text-mono-md text-on-surface"
                />
              </div>
            </div>

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
                {applyState === "error" && applyErrorMsg && (
                  <div className="my-md">
                    <Banner tone="danger" testId="apply-modal-error">
                      {t("applyFailed", { reason: applyErrorMsg })}
                    </Banner>
                  </div>
                )}
                <div className="flex justify-end gap-sm">
                  <Button
                    variant="secondary"
                    data-testid="cancel-apply-btn"
                    disabled={applying}
                    onClick={() => {
                      if (applying) return;
                      setShowApplyModal(false);
                      setAdminPassword("");
                    }}
                  >
                    {t("cancel")}
                  </Button>
                  <Button
                    variant="primary"
                    data-testid="confirm-apply-btn"
                    disabled={!adminPassword.trim() || applying}
                    onClick={handleConfirmApply}
                  >
                    {applying ? t("applying") : t("confirmApply")}
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
