import type { ReactNode } from "react";
import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";

export interface MenuAction {
  label: string;
  onSelect?: () => void;
  disabled?: boolean;
}

export function DropdownMenu({
  trigger,
  items,
  ariaLabel,
}: {
  trigger: ReactNode;
  items: MenuAction[];
  ariaLabel: string;
}) {
  return (
    <DropdownMenuPrimitive.Root>
      <DropdownMenuPrimitive.Trigger asChild>{trigger}</DropdownMenuPrimitive.Trigger>
      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content
          aria-label={ariaLabel}
          sideOffset={4}
          className="z-50 min-w-[10rem] rounded-lg border border-outline bg-surface-raised p-sm text-on-surface shadow-lg"
        >
          {items.map((item) => (
            <DropdownMenuPrimitive.Item
              key={item.label}
              disabled={item.disabled}
              onSelect={item.onSelect}
              className="cursor-default select-none rounded-sm px-md py-sm font-ui text-body-sm outline-none data-[highlighted]:bg-surface-hover data-[disabled]:opacity-50"
            >
              {item.label}
            </DropdownMenuPrimitive.Item>
          ))}
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  );
}
