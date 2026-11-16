import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router";
import {
  Globe,
  LogOut,
  Network,
  Palette,
  ShieldCheck,
  Type,
} from "lucide-react";
import { useI18n } from "../../i18n";
import { useTheme, type ThemePreference } from "../../theme";
import { useAuth } from "../auth/useAuth";
import { useApiClient } from "../../shared/api/client_context";
import { Banner, Button, Dialog, Select, StatusBadge } from "../../shared/ui";
import { useFontSetsQuery } from "../profiles/useProfilesQuery";
import { formatFontSetDisplayName } from "./SettingsPage";

function Block({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-md rounded-lg border border-outline bg-surface-subtle p-lg">
      <div className="flex items-center gap-sm">
        <span className="text-on-surface-muted">{icon}</span>
        <h2 className="font-ui text-title-sm text-on-surface">{title}</h2>
      </div>
      {children}
    </section>
  );
}

export function SettingsDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { locale, setLocale, t } = useI18n();
  const { preference, setPreference } = useTheme();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const client = useApiClient();
  const fontSetsQuery = useFontSetsQuery(client);
  const fontSets = fontSetsQuery.data?.items ?? null;
  const fontSetsError = fontSetsQuery.isError;
  const [healthStatus, setHealthStatus] = useState<
    "checking" | "healthy" | "error"
  >("checking");

  useEffect(() => {
    if (!open) return;
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
  }, [client, open]);

  const themeOptions = [
    { value: "system", label: t("themeSystem") },
    { value: "light", label: t("themeLight") },
    { value: "dark", label: t("themeDark") },
  ];

  const handleLogout = async () => {
    try {
      await logout();
    } catch {
      // Auth state is cleared locally; route guard redirects.
    }
    onOpenChange(false);
    navigate("/login");
  };

  return (
    <Dialog
      trigger={<span />}
      title={t("navSettings")}
      size="lg"
      open={open}
      onOpenChange={onOpenChange}
    >
      <div
        data-testid="settings-dialog"
        className="grid grid-cols-1 gap-md md:grid-cols-2"
      >
        <Block
          icon={<Palette aria-hidden="true" className="size-(--component-icon-lg-size)" />}
          title={t("appearance")}
        >
          <Select
            ariaLabel={t("theme")}
            value={preference}
            onValueChange={(value) => setPreference(value as ThemePreference)}
            options={themeOptions}
          />
        </Block>

        <Block
          icon={<Globe aria-hidden="true" className="size-(--component-icon-lg-size)" />}
          title={t("language")}
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
        </Block>

        <Block
          icon={<ShieldCheck aria-hidden="true" className="size-(--component-icon-lg-size)" />}
          title={t("controlApiStatusTitle")}
        >
          <div className="flex flex-wrap items-center justify-between gap-sm">
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
            <Button
              data-testid="settings-logout"
              variant="secondary"
              size="sm"
              onClick={handleLogout}
            >
              <LogOut aria-hidden="true" className="size-(--component-icon-sm-size)" />
              <span>{t("logOut")}</span>
            </Button>
          </div>
        </Block>

        <Block
          icon={<Network aria-hidden="true" className="size-(--component-icon-lg-size)" />}
          title={t("networkAccess")}
        >
          <div className="flex flex-col gap-sm">
            <div className="flex flex-wrap items-center justify-between gap-sm rounded-md border border-outline bg-surface p-md font-ui text-body-sm">
              <div className="flex flex-col gap-xs">
                <span className="font-ui text-label-md text-on-surface-muted">
                  {t("currentAccessAddress")}
                </span>
                <span
                  data-testid="network-current-address"
                  className="font-mono text-mono-md text-on-surface"
                >
                  {window.location.origin}
                </span>
              </div>
              <div className="flex flex-col gap-xs">
                <span className="font-ui text-label-md text-on-surface-muted">
                  {t("httpsPort")}
                </span>
                <span
                  data-testid="network-current-port"
                  className="font-mono text-mono-md text-on-surface"
                >
                  {window.location.port || "443"}
                </span>
              </div>
            </div>
            <p className="font-ui text-body-sm text-on-surface-muted">
              {t("networkDeployTimeNote")}
            </p>
          </div>
        </Block>

        <div className="md:col-span-2">
          <Block
            icon={<Type aria-hidden="true" className="size-(--component-icon-lg-size)" />}
            title={t("platformFontSets")}
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
              <div data-testid="font-sets" className="grid grid-cols-1 gap-sm md:grid-cols-2">
                {fontSets.map((fontSet) => {
                  const platformLabel =
                    fontSet.platform === "windows"
                      ? t("formPlatformWindows")
                      : fontSet.platform === "macos"
                        ? t("formPlatformMacos")
                        : fontSet.platform;
                  return (
                    <div
                      key={`${fontSet.platform}-${fontSet.set_id}`}
                      data-testid={`font-set-${fontSet.platform}-${fontSet.set_id}`}
                      className="rounded-md border border-outline bg-surface p-md"
                    >
                      <div className="mb-sm flex flex-wrap items-center justify-between gap-sm">
                        <div className="flex items-center gap-sm">
                          <span className="font-ui text-label-md text-on-surface">
                            {formatFontSetDisplayName(fontSet, t)}
                          </span>
                          <span className="rounded-sm bg-surface-subtle px-xs py-2xs font-ui text-label-sm text-on-surface-muted">
                            {platformLabel}
                          </span>
                        </div>
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
                          <dt className="text-on-surface-muted">
                            {t("fontSetFileCount")}
                          </dt>
                          <dd className="font-mono text-mono-md text-on-surface">
                            {fontSet.file_count}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-on-surface-muted">
                            {t("fontSetUsedBy")}
                          </dt>
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
                  );
                })}
              </div>
            )}
          </Block>
        </div>
      </div>
    </Dialog>
  );
}
