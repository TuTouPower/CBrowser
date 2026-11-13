import type { ReactNode } from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";

export function Tooltip({
  children,
  content,
}: {
  children: ReactNode;
  content: string;
}) {
  return (
    <TooltipPrimitive.Provider delayDuration={200}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            role="tooltip"
            sideOffset={4}
            className="z-[70] rounded-sm bg-surface-raised px-sm py-2xs font-ui text-label-sm text-on-surface shadow-lg"
          >
            {content}
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}
