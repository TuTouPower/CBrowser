import type { ReactNode } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "./cn";

export function Dialog({
  trigger,
  title,
  children,
  open,
  onOpenChange,
  contentClassName,
}: {
  trigger: ReactNode;
  title: string;
  children: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  contentClassName?: string;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Trigger asChild>{trigger}</DialogPrimitive.Trigger>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-none z-40 bg-overlay" />
        <DialogPrimitive.Content
          aria-modal="true"
          aria-describedby={undefined}
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-dialog-width max-w-dialog -translate-x-1/2 -translate-y-1/2 rounded-xl border border-outline bg-surface-raised p-lg text-on-surface shadow-xl",
            "focus:outline-none",
            contentClassName,
          )}
        >
          <DialogPrimitive.Title className="font-ui text-headline-md">
            {title}
          </DialogPrimitive.Title>
          <div className="mt-md">{children}</div>
          <DialogPrimitive.Close asChild>
            <button
              type="button"
              aria-label="Close"
              className="absolute right-md top-md rounded-sm p-xs text-on-surface-muted hover:bg-surface-hover focus-visible:outline-2 focus-visible:outline-focus"
            >
              <X aria-hidden="true" className="size-(--component-icon-md-size)" />
            </button>
          </DialogPrimitive.Close>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
