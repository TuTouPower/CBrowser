import * as SwitchPrimitive from "@radix-ui/react-switch";
import { cn } from "./cn";

export interface SwitchProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: string;
  disabled?: boolean;
  className?: string;
}

export function Switch({
  checked,
  onCheckedChange,
  label,
  disabled,
  className,
}: SwitchProps) {
  return (
    <SwitchPrimitive.Root
      checked={checked}
      onCheckedChange={onCheckedChange}
      disabled={disabled}
      aria-label={label}
      className={cn(
        "relative inline-flex h-(--component-switch-height) w-(--component-switch-width) shrink-0 items-center rounded-full bg-surface-subtle",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-50",
        "data-[state=checked]:bg-accent",
        className,
      )}
    >
      <SwitchPrimitive.Thumb className="block size-(--component-switch-size) translate-x-(--spacing-2xs) rounded-full bg-surface-raised transition-transform data-[state=checked]:translate-x-[calc(var(--component-switch-width)_-_var(--component-switch-size)_-_var(--spacing-2xs))]" />
    </SwitchPrimitive.Root>
  );
}
