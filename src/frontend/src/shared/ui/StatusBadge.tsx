import type { ReactNode } from "react";
import { AlertTriangle, CircleCheck, CircleX, LoaderCircle, MinusCircle } from "lucide-react";
import { cn } from "./cn";

export type StatusTone = "running" | "transition" | "error" | "stopped";

const TONES: Record<StatusTone, { className: string; icon: ReactNode }> = {
  running: {
    className: "bg-accent-soft text-on-surface",
    icon: <CircleCheck aria-hidden="true" className="size-(--component-icon-xs-size)" />,
  },
  transition: {
    className: "bg-warning-soft text-on-surface",
    icon: <LoaderCircle aria-hidden="true" className="size-(--component-icon-xs-size) animate-pulse" />,
  },
  error: {
    className: "bg-danger-soft text-on-surface",
    icon: <CircleX aria-hidden="true" className="size-(--component-icon-xs-size)" />,
  },
  stopped: {
    className: "bg-surface-subtle text-on-surface-muted",
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

export function RegionCode({ code }: { code: string }) {
  return (
    <span className="inline-flex items-center rounded-sm bg-surface-subtle px-sm py-2xs font-mono text-mono-md text-on-surface">
      {code}
    </span>
  );
}

export function WarningIcon({ className }: { className?: string }) {
  return <AlertTriangle aria-hidden="true" className={cn("size-(--component-icon-md-size)", className)} />;
}
