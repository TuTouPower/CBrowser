import { useI18n } from "../i18n";

interface StatusIndicatorProps {
  status: "running" | "stopped" | "initializing";
  size?: "sm" | "md";
}

export function StatusIndicator({ status, size = "sm" }: StatusIndicatorProps) {
  const { t } = useI18n();
  const sizeClass = size === "sm" ? "h-2 w-2" : "h-2.5 w-2.5";
  const isRunning = status === "running";
  const isInitializing = status === "initializing";
  const pulse = isRunning || isInitializing;
  const color = isRunning
    ? "bg-emerald-400"
    : isInitializing
      ? "bg-amber-400"
      : "bg-gray-500";
  const title = isInitializing
    ? t("firstTimeSetup")
    : status === "running"
      ? t("statusRunning")
      : t("statusStopped");

  return (
    <span className="relative inline-flex" title={title}>
      {pulse && (
        <span
          className={`absolute inline-flex ${sizeClass} rounded-full ${color} opacity-75 animate-ping`}
        />
      )}
      <span className={`relative inline-flex ${sizeClass} rounded-full ${color}`} />
    </span>
  );
}
