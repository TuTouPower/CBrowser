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
import { useI18n, type TranslationKey } from "../../i18n";
import { useTheme, type ThemePreference } from "../../theme";
import { useAuth } from "../auth/useAuth";
import { useApiClient } from "../../shared/api/client_context";
import type { FontSetInfo } from "../../shared/api/types";
import { Banner, Button, Select, StatusBadge } from "../../shared/ui";
import { useFontSetsQuery } from "../profiles/useProfilesQuery";

function Section({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-outline bg-surface p-lg">
      <div className="mb-md flex items-center gap-sm">
        <span className="text-on-surface-muted">{icon}</span>
        <h2 className="font-ui text-title-sm text-on-surface">{title}</h2>
      </div>
      {children}
    </section>
  );
}

export function formatFontSetDisplayName(
  fontSet: Pick<FontSetInfo, "platform" | "set_id" | "source" | "source_version">,
  t: (key: TranslationKey, params?: Record<string, string | number>) => string,
): string {
  const hay = `${fontSet.set_id} ${fontSet.source ?? ""} ${fontSet.source_version ?? ""}`.toLowerCase();
  if (fontSet.platform === "macos") {
    return t("fontSetMacosCore");
  }
  if (hay.includes("cjk") || hay.includes("office") || hay.includes("zh") || hay.includes("yahei")) {
    return t("fontSetOfficeCjk");
  }
  if (fontSet.platform === "windows") {
    return t("fontSetWindowsCore");
  }
  return t("fontSetCustomPack", {
    platform:
      fontSet.platform === "windows"
        ? t("formPlatformWindows")
        : fontSet.platform === "macos"
          ? t("formPlatformMacos")
          : fontSet.platform,
  });
}

export function SettingsPage() {
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
    navigate("/login");
  };

  return (
    <div data-testid="settings-page" className="mx-auto w-full max-w-panel flex flex-col gap-md">
      <Section
        icon={<Palette aria-hidden="true" className="size-(--component-icon-lg-size)" />}
        title={t("appearance")}
      >
        <Select
          ariaLabel={t("theme")}
          value={preference}
          onValueChange={(value) => setPreference(value as ThemePreference)}
          options={themeOptions}
        />
      </Section>

      <Section
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
      </Section>

      <Section
        icon={<ShieldCheck aria-hidden="true" className="size-(--component-icon-lg-size)" />}
        title={t("controlApiStatusTitle")}
      >
        <div className="flex items-center justify-between gap-sm">
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
      </Section>

      <Section
        icon={<Network aria-hidden="true" className="size-(--component-icon-lg-size)" />}
        title={t("networkAccess")}
      >
        <div className="flex flex-col gap-sm">
          <div className="flex flex-wrap items-center justify-between gap-sm rounded-md border border-outline bg-surface-subtle p-md font-ui text-body-sm">
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
      </Section>

      <Section
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
          <div data-testid="font-sets" className="flex flex-col gap-sm">
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
                  className="rounded-md border border-outline bg-surface-subtle p-md"
                >
                  <div className="mb-sm flex items-center justify-between gap-sm">
                    <div className="flex items-center gap-sm">
                      <span className="font-ui text-label-md text-on-surface">
                        {formatFontSetDisplayName(fontSet, t)}
                      </span>
                      <span className="rounded-sm bg-surface px-xs py-2xs font-ui text-label-sm text-on-surface-muted">
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
                      <dt className="text-on-surface-muted">{t("fontSetSource")}</dt>
                      <dd className="font-ui text-body-sm text-on-surface">
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
              );
            })}
          </div>
        )}
      </Section>
    </div>
  );
}
