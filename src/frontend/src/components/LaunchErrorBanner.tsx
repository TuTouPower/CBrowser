import { AlertTriangle, X } from "lucide-react";
import { api, type LaunchDenial } from "../lib/api";
import { useI18n } from "../i18n";

export function LaunchErrorBanner({
  error,
  onDismiss,
}: {
  error: LaunchDenial;
  onDismiss: () => void;
}) {
  const { t } = useI18n();
  const openUpgrade = () => {
    if (!error.upgrade_url) return;
    api.openExternal(error.upgrade_url).catch(() => {});
  };

  return (
    <div className="flex items-center justify-center gap-2 px-4 py-1.5 text-xs bg-red-500/10 border-b border-red-500/30 text-red-300">
      <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
      <span>{error.message}</span>
      {error.upgrade_url && (
        <button
          onClick={openUpgrade}
          className="font-medium underline underline-offset-2 hover:text-red-200"
        >
          {t("upgradePlan")}
        </button>
      )}
      <button
        onClick={onDismiss}
        className="ml-1 p-0.5 text-red-400/70 hover:text-red-200"
        title={t("dismiss")}
        aria-label={t("dismissLaunchError")}
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
