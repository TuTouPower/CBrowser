import { useState } from "react";
import { Code2 } from "lucide-react";
import { useI18n } from "../i18n";

interface CdpEndpointButtonProps {
  cdpUrl: string | null;
}

export function CdpEndpointButton({ cdpUrl }: CdpEndpointButtonProps) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  if (!cdpUrl) return null;

  const copyEndpoint = () => {
    const endpoint = `${window.location.protocol}//${window.location.host}${cdpUrl}`;
    navigator.clipboard?.writeText(endpoint).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }).catch((error) => console.warn("[cdp] copy failed:", error));
  };

  return (
    <button
      onClick={copyEndpoint}
      className={`p-1 ${copied ? "text-emerald-400" : "text-gray-500 hover:text-gray-300"}`}
      title={copied ? t("copied") : t("copyCdpUrl")}
    >
      <Code2 className="h-3.5 w-3.5" />
    </button>
  );
}
