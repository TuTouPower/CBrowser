import { Play, Square, Loader2 } from "lucide-react";
import { useState } from "react";
import { useI18n } from "../i18n";

interface LaunchButtonProps {
  status: "running" | "stopped" | "initializing";
  onLaunch: () => Promise<void>;
  onStop: () => Promise<void>;
}

export function LaunchButton({ status, onLaunch, onStop }: LaunchButtonProps) {
  const { t } = useI18n();
  const [loading, setLoading] = useState(false);

  const handleClick = async () => {
    setLoading(true);
    try {
      if (status === "running") {
        await onStop();
      } else {
        await onLaunch();
      }
    } catch (err) {
      console.error("Action failed:", err);
    } finally {
      setLoading(false);
    }
  };

  if (loading || status === "initializing") {
    const label =
      status === "initializing"
        ? t("firstTimeSetup")
        : status === "running"
          ? t("stopping")
          : t("launching");
    return (
      <button disabled className="btn-secondary opacity-60 cursor-not-allowed flex items-center gap-1.5">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        <span>{label}</span>
      </button>
    );
  }

  if (status === "running") {
    return (
      <button onClick={handleClick} className="btn-danger flex items-center gap-1.5">
        <Square className="h-3.5 w-3.5" />
        <span>{t("stop")}</span>
      </button>
    );
  }

  return (
    <button onClick={handleClick} className="btn-primary flex items-center gap-1.5">
      <Play className="h-3.5 w-3.5" />
      <span>{t("launch")}</span>
    </button>
  );
}
