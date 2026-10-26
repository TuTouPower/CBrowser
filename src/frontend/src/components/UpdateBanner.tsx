import { ArrowUpCircle, X } from "lucide-react";
import { api, type UpdateInfo } from "../lib/api";
import { useI18n } from "../i18n";

export function UpdateBanner({
  info,
  onDismiss,
}: {
  info: UpdateInfo;
  onDismiss: () => void;
}) {
  const { t } = useI18n();
  const openRelease = () => {
    if (!info.release_url) return;
    api.openExternal(info.release_url).catch(() => {});
  };

  return (
    <div className="flex items-center justify-center gap-2 px-4 py-1.5 text-xs bg-cyan-500/10 border-b border-cyan-500/30 text-cyan-300">
      <ArrowUpCircle className="h-3.5 w-3.5 flex-shrink-0" />
      <span>{t("updateAvailable", { version: info.latest ?? "" })}</span>
      <button
        onClick={openRelease}
        className="font-medium underline underline-offset-2 hover:text-cyan-200"
      >
        {t("download")}
      </button>
      <button
        onClick={onDismiss}
        className="ml-1 p-0.5 text-cyan-400/70 hover:text-cyan-200"
        title={t("dismiss")}
        aria-label={t("dismissUpdate")}
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
