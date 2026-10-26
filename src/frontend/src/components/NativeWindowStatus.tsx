import { ExternalLink, Monitor } from "lucide-react";
import { useEffect, useState } from "react";
import { CdpEndpointButton } from "./CdpEndpointButton";
import { useI18n } from "../i18n";

interface NativeWindowStatusProps {
  profileName: string;
  cdpUrl: string | null;
  profileId?: string;
  capturePreview?: boolean;
}

const PREVIEW_REFRESH_MS = 15000;

export function NativeWindowStatus({
  profileName,
  cdpUrl,
  profileId,
  capturePreview,
}: NativeWindowStatusProps) {
  const { t } = useI18n();
  const [buster, setBuster] = useState(() => Date.now());
  const [loaded, setLoaded] = useState(false);

  const showPreview = Boolean(profileId) && capturePreview !== false;

  useEffect(() => {
    if (!showPreview) return;
    const id = setInterval(() => setBuster(Date.now()), PREVIEW_REFRESH_MS);
    return () => clearInterval(id);
  }, [showPreview]);

  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="max-w-lg rounded-xl border border-border bg-surface-1 p-8 text-center">
        {showPreview && (
          <img
            src={`/api/profiles/${profileId}/screenshot?t=${buster}`}
            onLoad={() => setLoaded(true)}
            alt={t("liveBrowserPreview")}
            className={`mb-6 w-full rounded-lg border border-border ${loaded ? "" : "hidden"}`}
          />
        )}
        <Monitor className="mx-auto mb-4 h-10 w-10 text-accent" />
        <h2 className="text-lg font-medium text-gray-100">{t("openedInNativeWindow")}</h2>
        <p className="mt-2 text-sm text-gray-400">
          {t("nativeWindowHint", { name: profileName })}
        </p>
        <div className="mt-5 flex items-center justify-center gap-2 text-xs text-gray-500">
          <ExternalLink className="h-3.5 w-3.5" />
          <span>{t("automationViaCdp")}</span>
          <CdpEndpointButton cdpUrl={cdpUrl} />
        </div>
      </div>
    </div>
  );
}
