import { useEffect, useRef, useState } from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { SearchField } from "./Input";
import {
  SelectItem,
  SelectTrigger,
  type SelectOption,
} from "./Select";

/**
 * Searchable select for growing collections (proxies, environments,
 * groups, countries, cities): the popup is bounded to the available
 * viewport height (t077 AC-003/AC-004) and the search filters the full
 * candidate array client-side, so an item that was never rendered
 * into the scroll viewport is still findable.
 *
 * Commit semantics are the same as `Select` (see `SelectItem`): a
 * pick is recorded via `onOptionSelect` even when it re-selects the
 * current value, while `onValueChange` only fires on a real change.
 * Keyboard: typing filters; ArrowDown/Up move focus into the list
 * (Radix); Home/End in the search box keep their caret meaning
 * (t077_gen_f001) and only jump to the first/last option once focus
 * is in the list; Enter while typing picks the first match;
 * Escape closes and returns focus to the trigger.
 */
export interface SearchableSelectProps {
  value?: string;
  onValueChange?: (value: string) => void;
  onOptionSelect?: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  ariaLabel: string;
  searchPlaceholder: string;
  noResultsLabel: string;
  disabled?: boolean;
  className?: string;
}

export function SearchableSelect({
  value,
  onValueChange,
  onOptionSelect,
  options,
  placeholder,
  ariaLabel,
  searchPlaceholder,
  noResultsLabel,
  disabled,
  className,
}: SearchableSelectProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  // Whether the search box should own focus. Set when the menu
  // opens; cleared once the user moves focus into the list (input
  // blur) so later re-renders never yank focus back out of the list.
  const focusSearchRef = useRef(false);
  const query = search.trim().toLowerCase();
  const filtered = query
    ? options.filter((option) => option.label.toLowerCase().includes(query))
    : options;

  // Focus the search box when the menu opens so the user can type
  // immediately. Radix focuses the selected item (or the content) in
  // its own effect once the popper is positioned, which happens a
  // commit after open — so the focus is set twice: once on the open
  // commit and once on a zero-delay timer that runs after Radix's
  // positioning commit. The flag is cleared on input blur, so the
  // timer never steals focus back once the user has moved into the
  // list.
  useEffect(() => {
    if (!open) return;
    if (focusSearchRef.current) searchRef.current?.focus();
    const timer = setTimeout(() => {
      if (focusSearchRef.current) searchRef.current?.focus();
    }, 0);
    return () => clearTimeout(timer);
  }, [open ]);

  function handleOpenChange(next: boolean) {
    focusSearchRef.current = next;
    setOpen(next);
    if (!next) setSearch("");
  }

  // Enter while typing picks the first match. Radix only commits
  // Enter when focus is on an item, so the search box needs its own
  // commit; it mirrors Radix's split: onValueChange only on a real
  // change, onOptionSelect for every explicit pick.
  function selectFirstMatch() {
    const first = filtered[0];
    if (!first) return;
    if (first.value !== value) onValueChange?.(first.value);
    onOptionSelect?.(first.value);
    setSearch("");
    setOpen(false);
  }

  return (
    <SelectPrimitive.Root
      value={value}
      onValueChange={onValueChange}
      open={open}
      onOpenChange={handleOpenChange}
      disabled={disabled}
    >
      <SelectTrigger
        value={value}
        options={options}
        placeholder={placeholder}
        ariaLabel={ariaLabel}
        className={className}
      />
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={4}
          className="z-50 max-h-available-height min-w-select overflow-hidden rounded-lg border border-outline bg-surface-raised text-on-surface shadow-lg"
        >
          <div className="border-b border-outline p-sm">
            <SearchField
              ref={searchRef}
              label={searchPlaceholder}
              placeholder={searchPlaceholder}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              onFocus={() => {
                focusSearchRef.current = true;
              }}
              onBlur={() => {
                focusSearchRef.current = false;
              }}
              onKeyDown={(event) => {
                // Stop printable keys from reaching Radix's typeahead:
                // it would yank focus out of the search box onto the
                // first matching item mid-typing. Home/End also stop
                // here: Radix's Content handler would otherwise
                // preventDefault them and yank focus to the first/last
                // option, stealing the caret from the search box
                // (t077_gen_f001). ArrowDown/ArrowUp keep bubbling so
                // Radix moves focus into the list.
                if (event.key.length === 1 || event.key === "Home" || event.key === "End") {
                  event.stopPropagation();
                }
                if (event.key === "Enter") {
                  event.preventDefault();
                  selectFirstMatch();
                }
              }}
            />
          </div>
          <SelectPrimitive.Viewport className="p-sm">
            {filtered.map((option) => (
              <SelectItem
                key={option.value}
                option={option}
                onOptionSelect={onOptionSelect}
              />
            ))}
            {filtered.length === 0 && (
              <div className="flex h-(--component-menu-item-height) items-center px-md font-ui text-body-md text-on-surface-muted">
                {noResultsLabel}
              </div>
            )}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
