import { useState } from "react";
import { Link, useParams } from "react-router";
import { ArrowLeft, Check, Copy, Cpu } from "lucide-react";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import { useProfileQuery } from "../profiles/useProfilesQuery";
import { useAutomationQuery } from "./useAutomation";

function absoluteWebSocketUrl(path: string): string {
  if (typeof window === "undefined") return path;
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}${path}`;
}

export function ProfileAutomationPage() {
  const { profileId } = useParams<{ profileId: string }>();
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const client = useApiClient();
  const { data: profile } = useProfileQuery(profileId, client);
  const automation = useAutomationQuery(profileId, client);

  if (!profileId) {
    return <div className="p-8 text-gray-400 text-sm">{t("profileNotFoundOrFailed")}</div>;
  }

  const endpoint = automation.data
    ? absoluteWebSocketUrl(automation.data.cdp_ws_path)
    : "";

  const copyEndpoint = async () => {
    if (!endpoint) return;
    try {
      await navigator.clipboard.writeText(endpoint);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div data-testid="profile-automation-page" className="p-8 max-w-3xl mx-auto">
      <Link
        to={`/session/${profileId}`}
        className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 mb-6"
      >
        <ArrowLeft className="h-4 w-4" />
        {t("backToSession")}
      </Link>

      <div className="bg-surface-1 border border-border rounded-lg p-6">
        <h1 className="text-lg font-bold text-gray-100 flex items-center gap-2">
          <Cpu className="h-5 w-5 text-primary" />
          {t("automationPageTitle")}
        </h1>
        <p className="text-xs text-gray-400 mt-1 mb-5">
          {profile ? profile.name : profileId} — {t("automationPageHint")}
        </p>

        {automation.isLoading ? (
          <div className="py-8 text-center text-sm text-gray-400">{t("loading")}</div>
        ) : automation.error ? (
          <div role="alert" className="py-8 text-center text-sm text-red-400">
            {automation.error.message || t("failedToLoadAutomation")}
          </div>
        ) : automation.data ? (
          <dl className="space-y-4 text-sm">
            <div>
              <dt className="text-xs text-gray-400 mb-1">{t("automationEndpoint")}</dt>
              <dd className="flex items-center gap-2">
                <code
                  data-testid="automation-endpoint"
                  className="flex-1 min-w-0 truncate rounded bg-surface-2 border border-border px-2 py-1.5 text-xs text-primary"
                >
                  {endpoint}
                </code>
                <button
                  type="button"
                  onClick={() => void copyEndpoint()}
                  className="inline-flex items-center gap-1 px-2 py-1.5 rounded text-xs bg-surface-2 hover:bg-surface-3 border border-border text-gray-300"
                  aria-label={t("copyEndpoint")}
                >
                  {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  {copied ? t("copied") : t("copy")}
                </button>
              </dd>
              <p className="text-[11px] text-gray-500 mt-1">
                {t("automationTokenHeader", { value: automation.data.token_header })}
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div data-testid="automation-runtime-state">
                <dt className="text-xs text-gray-400 mb-1">{t("automationRuntimeState")}</dt>
                <dd className="text-gray-200">
                  {automation.data.runtime_observed_state === "running"
                    ? t("statusRunning")
                    : automation.data.runtime_observed_state === "stopped"
                      ? t("statusStopped")
                      : automation.data.runtime_observed_state}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-gray-400 mb-1">{t("automationRuntimeInstance")}</dt>
                <dd className="text-gray-200 truncate">
                  {automation.data.runtime_instance_id || "—"}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-gray-400 mb-1">{t("automationSupervisor")}</dt>
                <dd className={automation.data.supervisor_configured ? "text-green-400" : "text-yellow-400"}>
                  {automation.data.supervisor_configured
                    ? t("automationSupervisorReady")
                    : t("automationSupervisorMissing")}
                </dd>
              </div>
            </div>
          </dl>
        ) : null}
      </div>
    </div>
  );
}
