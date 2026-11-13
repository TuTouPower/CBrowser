import { useRef } from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "./cn";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps {
  value?: string;
  onValueChange?: (value: string) => void;
  /**
   * Fires for every committed option pick, including re-picking the
   * value that is already selected. Radix only calls `onValueChange`
   * when the value changes, so a pick that confirms the current value
   * is invisible to `onValueChange` — callers that must record "the
   * user explicitly chose this, even if it was already showing" use
   * this (t053: the font-set "none" pick made before the backend
   * default arrives).
   *
   * All three commit paths are covered, matching the funnel Radix
   * itself uses (2.4.1): mouse pointer picks via `onPointerUp`
   * (only when `event.pointerType === "mouse"` and the press started
   * on this same item — a pointerup that lands here after a press
   * elsewhere is not a Radix commit and must not count as a pick),
   * touch/pen picks via `onClick`, and keyboard picks (Enter/Space)
   * via `onKeyDown` using the same selection keys Radix itself uses. Radix 2.4.1 has
   * no `onSelect` prop on `SelectItem`, so there is no single Radix
   * callback that fires for every commit — the three handlers
   * together are the equivalent.
   *
   * `onClick` alone cannot cover the mouse path: a real browser
   * dispatches pointerdown → pointerup → click, Radix commits on
   * pointerup and closes the menu synchronously, and the click that
   * follows is dispatched to an item that is already unmounted, so
   * React never sees it. The `onPointerUp` handler runs before
   * Radix's own close (user handlers compose first), while the item
   * is still mounted. The keyboard handler mirrors Radix's own guard
   * (`event.target` must be the item itself); a Space pressed while a
   * typeahead search is in progress still counts as a pick here
   * (Radix would treat it as search continuation) — the only effect
   * is that the currently shown value is recorded as explicitly
   * chosen, which is the safe direction for a guard like this.
   */
  onOptionSelect?: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  ariaLabel: string;
  disabled?: boolean;
  className?: string;
}

export function Select({
  value,
  onValueChange,
  onOptionSelect,
  options,
  placeholder,
  ariaLabel,
  disabled,
  className,
}: SelectProps) {
  return (
    <SelectPrimitive.Root
      value={value}
      onValueChange={onValueChange}
      disabled={disabled}
    >
      <SelectPrimitive.Trigger
        aria-label={ariaLabel}
        className={cn(
          "inline-flex h-9 items-center justify-between gap-sm rounded-md border border-outline bg-surface px-md font-ui text-body-md text-on-surface",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-50",
          className,
        )}
      >
        <SelectPrimitive.Value placeholder={placeholder} />
        <SelectPrimitive.Icon>
          <ChevronDown aria-hidden="true" className="h-4 w-4" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={4}
          className="z-50 min-w-select overflow-hidden rounded-lg border border-outline bg-surface-raised text-on-surface shadow-lg"
        >
          <SelectPrimitive.Viewport className="p-sm">
            {options.map((option) => (
              <SelectItem
                key={option.value}
                option={option}
                onOptionSelect={onOptionSelect}
              />
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}

function SelectItem({
  option,
  onOptionSelect,
}: {
  option: SelectOption;
  onOptionSelect?: (value: string) => void;
}) {
  // Whether the current mouse press started on this item. Radix only
  // commits a mouse pick on pointerup when this item's own
  // pointerTypeRef is "mouse" (dist :987-991: set by this item's own
  // pointerdown/move, initial "touch"); a pointerup that lands here
  // after a press elsewhere (drag-across release, or a press on the
  // trigger dragged into the menu) is not a commit, so it must not
  // count as an explicit pick (t053_code_f006). The ref is per item
  // because the press state belongs to the item, not the list.
  const pressedRef = useRef(false);
  return (
    <SelectPrimitive.Item
      value={option.value}
      onClick={() => onOptionSelect?.(option.value)}
      onPointerDown={(event) => {
        if (event.pointerType === "mouse") {
          pressedRef.current = true;
        }
      }}
      onPointerUp={(event) => {
        // Mouse only: Radix commits a mouse pick on pointerup
        // (dist :979-985) and unmounts the menu before the
        // click is dispatched, so this is the only handler
        // that can see a mouse pick. Touch/pen stay on
        // onClick (Radix commits those on click, :973-977).
        // Only fire when the press started on this item.
        if (event.pointerType === "mouse" && pressedRef.current) {
          onOptionSelect?.(option.value);
        }
        pressedRef.current = false;
      }}
      onPointerLeave={() => {
        pressedRef.current = false;
      }}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        if (event.key === "Enter" || event.key === " ") {
          onOptionSelect?.(option.value);
        }
      }}
      className="relative flex h-8 cursor-default select-none items-center rounded-sm pl-xl pr-sm font-ui text-body-md outline-none data-[highlighted]:bg-surface-hover"
    >
      <SelectPrimitive.ItemIndicator className="absolute left-sm">
        <Check aria-hidden="true" className="h-3.5 w-3.5" />
      </SelectPrimitive.ItemIndicator>
      <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  );
}
