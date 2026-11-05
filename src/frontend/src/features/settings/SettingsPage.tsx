import { useState, useEffect } from "react";
import { Link } from "react-router";
import { ArrowLeft, Settings, ShieldCheck, Globe } from "lucide-react";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";

export function SettingsPage() {
  const { locale, setLocale, t } = useI18n();
  const client = useApiClient();
  const [healthStatus, setHealthStatus] = useState<string>("checking");

  useEffect(() => {
    client.health
      .check()
      .then(() => setHealthStatus("healthy"))
      .catch(() => setHealthStatus("error"));
  }, [client]);

  return (
    <div data-testid="settings-page" className="p-8 max-w-3xl mx-auto">
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 mb-6"
      >
        <ArrowLeft className="h-4 w-4" />
        {t("backToDashboard")}
      </Link>

      <div className="flex items-center gap-3 mb-6">
        <Settings className="h-6 w-6 text-primary" />
        <h1 className="text-xl font-bold text-gray-100">{t("settings")}</h1>
      </div>

      <div className="space-y-6">
        {/* Language setting */}
        <div className="bg-surface-1 border border-border rounded-lg p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Globe className="h-5 w-5 text-gray-400" />
              <div>
                <h3 className="text-sm font-medium text-gray-200">{t("language")}</h3>
                <p className="text-xs text-gray-400">{t("switchLanguage")}</p>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setLocale("en")}
                className={`px-3 py-1.5 rounded text-xs font-medium border ${
                  locale === "en"
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-surface-2 text-gray-300 border-border hover:bg-surface-3"
                }`}
              >
                {t("languageEn")}
              </button>
              <button
                type="button"
                onClick={() => setLocale("zh")}
                className={`px-3 py-1.5 rounded text-xs font-medium border ${
                  locale === "zh"
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-surface-2 text-gray-300 border-border hover:bg-surface-3"
                }`}
              >
                {t("languageZh")}
              </button>
            </div>
          </div>
        </div>

        {/* API System Status */}
        <div className="bg-surface-1 border border-border rounded-lg p-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <ShieldCheck className="h-5 w-5 text-gray-400" />
              <div>
                <h3 className="text-sm font-medium text-gray-200">
                  {t("controlApiStatusTitle")}
                </h3>
                <p className="text-xs text-gray-400">
                  {t("controlApiStatusHint")}
                </p>
              </div>
            </div>
            <div>
              {healthStatus === "healthy" && (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  {t("healthHealthy")}
                </span>
              )}
              {healthStatus === "checking" && (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  {t("healthChecking")}
                </span>
              )}
              {healthStatus === "error" && (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20">
                  {t("healthUnreachable")}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
