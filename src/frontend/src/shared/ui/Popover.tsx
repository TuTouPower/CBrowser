import type { ReactNode } from "react";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import { cn } from "./cn";

export function Popover({
  trigger,
  children,
  ariaLabel,
  contentClassName,
  open,
  onOpenChange,
}: {
  trigger: ReactNode;
  children: ReactNode;
  ariaLabel: string;
  contentClassName?: string;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  return (
    <PopoverPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <PopoverPrimitive.Trigger asChild>{trigger}</PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          aria-label={ariaLabel}
          sideOffset={4}
          className={cn(
            "z-50 w-72 rounded-lg border border-outline bg-surface-raised p-md text-on-surface shadow-lg",
            "focus:outline-none",
            contentClassName,
          )}
        >
          {children}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
