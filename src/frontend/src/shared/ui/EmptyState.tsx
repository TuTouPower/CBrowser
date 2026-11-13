import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div
      data-testid="empty-state"
      className="flex flex-col items-center justify-center gap-md rounded-lg border border-outline bg-surface px-xl py-2xl text-center"
    >
      <div className="text-on-surface-muted">{icon ?? <Inbox aria-hidden="true" className="size-(--component-icon-2xl-size)" />}</div>
      <h2 className="font-ui text-headline-md text-on-surface">{title}</h2>
      {description && (
        <p className="max-w-panel font-ui text-body-sm text-on-surface-muted">{description}</p>
      )}
      {action}
    </div>
  );
}
