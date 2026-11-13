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
   * Radix 2.4.1 has no `onSelect` prop on `SelectItem`, so no single
   * callback covers every commit. `onOptionSelect` mirrors Radix's own
   * commit criterion as one source of truth instead of tracking presses
   * (dist :861-947): each item keeps a `pointerTypeRef` (initial
   * "touch") that BOTH `pointerdown` and `pointermove` set to
   * `event.pointerType`. Radix commits on `pointerup` when that ref is
   * "mouse" (:909-916), on `click` when it is not "mouse" (:901-908),
   * and on Enter/Space via `onKeyDown` (:933-942). The three handlers
   * here fire for exactly those events. So a `pointerdown` on another
   * item followed by a `pointermove` onto this one makes a `pointerup`
   * here a Radix commit that is recorded too, even though no press
   * started on this item (p070 D case) — a guard that only watched
   * `pointerdown` missed these.
   *
   * `onClick` fires only when the ref is not "mouse", which keeps a
   * mouse pick committed on `pointerup` from firing twice via the
   * trailing `click` (touch/pen commit on that `click`). A real browser
   * dispatches pointerdown → pointerup → click and Radix closes the
   * menu on the mouse `pointerup`, so the trailing click usually lands
   * on an already-unmounted item — this guard does not depend on that
   * unmount. Radix never resets its ref on pointerup/pointerleave (the
   * item unmounts on close and the ref is recreated on reopen), so
   * neither do we: resetting would make the trailing mouse click look
   * non-mouse and double-fire. The keyboard handler mirrors Radix's
   * guard (`event.target` must be the item itself); a Space pressed
   * while a typeahead search is in progress still counts as a pick
   * here (Radix would treat it as search continuation) — the only
   * effect is recording the shown value as explicitly chosen, which is
   * the safe direction for a guard like this.
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
          "inline-flex h-(--component-select-height) items-center justify-between gap-sm rounded-md border border-outline bg-surface px-md font-ui text-body-md text-on-surface",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-50",
          className,
        )}
      >
        <SelectPrimitive.Value placeholder={placeholder} />
        <SelectPrimitive.Icon>
          <ChevronDown aria-hidden="true" className="size-(--component-icon-md-size)" />
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
  // Mirror Radix 2.4.1's per-item commit criterion as the single
  // source of truth (dist :861-947). Both `pointerdown` and
  // `pointermove` set this ref to `event.pointerType` (initial
  // "touch"); Radix commits a mouse pick on `pointerup` when the ref
  // is "mouse" (:909-916) and a touch/pen pick on `click` when it is
  // not "mouse" (:901-908). onOptionSelect fires for exactly those
  // events. Radix never resets the ref on pointerup/pointerleave —
  // the item unmounts when the menu closes — and the `!== "mouse"`
  // click guard is what stops a mouse pointerup pick from firing a
  // second time via the trailing click; resetting would break both.
  const pointerTypeRef = useRef("touch");
  return (
    <SelectPrimitive.Item
      value={option.value}
      onClick={() => {
        if (pointerTypeRef.current !== "mouse") {
          onOptionSelect?.(option.value);
        }
      }}
      onPointerDown={(event) => {
        pointerTypeRef.current = event.pointerType;
      }}
      onPointerMove={(event) => {
        pointerTypeRef.current = event.pointerType;
      }}
      onPointerUp={() => {
        if (pointerTypeRef.current === "mouse") {
          onOptionSelect?.(option.value);
        }
      }}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        if (event.key === "Enter" || event.key === " ") {
          onOptionSelect?.(option.value);
        }
      }}
      className="relative flex h-(--component-menu-item-height) cursor-default select-none items-center rounded-sm pl-xl pr-sm font-ui text-body-md outline-none data-[highlighted]:bg-surface-hover"
    >
      <SelectPrimitive.ItemIndicator className="absolute left-sm">
        <Check aria-hidden="true" className="size-(--component-icon-sm-size)" />
      </SelectPrimitive.ItemIndicator>
      <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
    </SelectPrimitive.Item>
  );
}
