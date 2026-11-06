import type { ReactNode } from "react";
import { AlertTriangle, CircleX, X } from "lucide-react";
import { cn } from "./cn";

export function Banner({
  tone = "warning",
  children,
  onDismiss,
  testId,
}: {
  tone?: "warning" | "danger";
  children: ReactNode;
  onDismiss?: () => void;
  testId?: string;
}) {
  const Icon = tone === "danger" ? CircleX : AlertTriangle;
  return (
    <div
      data-testid={testId}
      role="alert"
      className={cn(
        "flex items-center gap-md rounded-md border px-md py-sm font-ui text-body-sm",
        tone === "danger"
          ? "border-danger bg-danger-soft text-on-surface"
          : "border-warning bg-warning-soft text-on-surface",
      )}
    >
      <Icon aria-hidden="true" className="h-4 w-4 shrink-0" />
      <div className="flex-1">{children}</div>
      {onDismiss && (
        <button
          type="button"
          aria-label="Dismiss"
          onClick={onDismiss}
          className="rounded-sm p-1 hover:bg-surface-hover focus-visible:outline-2 focus-visible:outline-focus"
        >
          <X aria-hidden="true" className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}
