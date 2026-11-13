import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import { Check } from "lucide-react";
import { cn } from "./cn";

export interface CheckboxProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: string;
  disabled?: boolean;
  className?: string;
}

export function Checkbox({
  checked,
  onCheckedChange,
  label,
  disabled,
  className,
}: CheckboxProps) {
  return (
    <CheckboxPrimitive.Root
      checked={checked}
      onCheckedChange={(value) => onCheckedChange(value === true)}
      disabled={disabled}
      aria-label={label}
      className={cn(
        "inline-flex size-(--component-checkbox-size) shrink-0 items-center justify-center rounded-sm border border-outline-strong bg-surface text-on-accent",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-50",
        "data-[state=checked]:bg-accent data-[state=checked]:border-accent",
        className,
      )}
    >
      <CheckboxPrimitive.Indicator>
        <Check aria-hidden="true" className="size-(--component-icon-xs-size)" />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
