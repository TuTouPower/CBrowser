import type { ReactNode } from "react";
import { AlertTriangle, CircleCheck, CircleX, Globe, LoaderCircle, MinusCircle } from "lucide-react";
import { regionFlagEmoji } from "../presentation";
import { cn } from "./cn";

export type StatusTone = "running" | "transition" | "error" | "stopped";

const TONES: Record<StatusTone, { className: string; icon: ReactNode }> = {
  running: {
    className: "border border-success bg-success-soft text-success",
    icon: <CircleCheck aria-hidden="true" className="size-(--component-icon-xs-size)" />,
  },
  transition: {
    className: "border border-warning bg-warning-soft text-warning",
    icon: <LoaderCircle aria-hidden="true" className="size-(--component-icon-xs-size) animate-pulse" />,
  },
  error: {
    className: "border border-danger bg-danger-soft text-danger",
    icon: <CircleX aria-hidden="true" className="size-(--component-icon-xs-size)" />,
  },
  stopped: {
    className: "border border-outline bg-surface-subtle text-on-surface-muted",
    icon: <MinusCircle aria-hidden="true" className="size-(--component-icon-xs-size)" />,
  },
};

export function StatusBadge({ tone, label }: { tone: StatusTone; label: string }) {
  const toneStyle = TONES[tone];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-xs rounded-sm px-sm py-2xs font-ui text-label-sm",
        toneStyle.className,
      )}
    >
      {toneStyle.icon}
      {label}
    </span>
  );
}

export type GroupHue =
  | "slate"
  | "blue"
  | "teal"
  | "green"
  | "amber"
  | "orange"
  | "red"
  | "violet";

const GROUP_HUES: Record<GroupHue, string> = {
  slate: "bg-group-slate",
  blue: "bg-group-blue",
  teal: "bg-group-teal",
  green: "bg-group-green",
  amber: "bg-group-amber",
  orange: "bg-group-orange",
  red: "bg-group-red",
  violet: "bg-group-violet",
};

export function GroupChip({
  label,
  hue = "slate",
}: {
  label: string;
  hue?: GroupHue;
}) {
  return (
    <span className="inline-flex items-center gap-sm rounded-sm bg-surface-subtle px-sm py-2xs font-ui text-label-sm text-on-surface">
      <span className={cn("size-(--component-group-chip-size) rounded-full", GROUP_HUES[hue])} aria-hidden="true" />
      {label}
    </span>
  );
}

export function ProtocolChip({ protocol }: { protocol: string }) {
  return (
    <span className="inline-flex items-center rounded-sm border border-outline px-sm py-2xs font-mono text-mono-caps uppercase text-on-surface-muted">
      {protocol}
    </span>
  );
}

export function RegionBadge({
  code,
  name,
  unknownLabel,
}: {
  code: string;
  /** Localized display name; falls back to the code itself. */
  name?: string | null;
  /** Accessible name used when the code is not a valid region code. */
  unknownLabel: string;
}) {
  const flag = regionFlagEmoji(code);
  if (flag === null) {
    // Unknown code: never fabricate a flag; one consistent placeholder
    // with a complete accessible name (t079 AC-005).
    return (
      <span
        role="img"
        aria-label={unknownLabel}
        className="inline-flex items-center gap-xs rounded-sm bg-surface-subtle px-sm py-2xs font-ui text-label-sm text-on-surface-muted"
      >
        <Globe aria-hidden="true" className="size-(--component-icon-xs-size)" />
        <span aria-hidden="true">{name ?? code}</span>
      </span>
    );
  }
  const displayName = name ?? code.toUpperCase();
  return (
    <span className="inline-flex items-center gap-xs rounded-sm bg-surface-subtle px-sm py-2xs font-ui text-label-sm text-on-surface">
      <span role="img" aria-label={displayName} className="leading-none">
        <span aria-hidden="true">{flag}</span>
      </span>
      <span>{displayName}</span>
    </span>
  );
}

export function WarningIcon({ className }: { className?: string }) {
  return <AlertTriangle aria-hidden="true" className={cn("size-(--component-icon-md-size)", className)} />;
}
