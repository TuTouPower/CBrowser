import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { useI18n } from "../../i18n";
import { cn } from "../../shared/ui/cn";
import { filterTimezones } from "./profile_locale";

/**
 * Timezone combobox (t053): type to filter IANA timezones, or open it and
 * scroll the full list; fully keyboard-operable. The first option is
 * "auto" (null timezone: follow the egress IP). Common timezones stay
 * pinned at the top of the list.
 */
export interface TimezoneComboboxProps {
  value: string | null;
  onValueChange: (value: string | null) => void;
  ariaLabel: string;
  testId?: string;
}

interface Option {
  key: string;
  label: string;
  value: string | null;
}

export function TimezoneCombobox({
  value,
  onValueChange,
  ariaLabel,
  testId,
}: TimezoneComboboxProps) {
  const { t } = useI18n();
  const listboxId = useId();
  const wrapperRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(value ?? "");
  const [activeIndex, setActiveIndex] = useState(0);

  // Keep the input in sync with the form value when it changes from
  // outside (e.g. a profile is loaded); while open, the user owns it.
  useEffect(() => {
    if (!open) {
      setQuery(value ?? "");
    }
  }, [value, open]);

  const options = useMemo<Option[]>(() => {
    const needle = query.trim().toLowerCase();
    const autoLabel = t("formTimezoneAuto");
    const autoMatches =
      needle === "" ||
      "auto".includes(needle) ||
      autoLabel.toLowerCase().includes(needle);
    const zones = filterTimezones(query);
    const list: Option[] = autoMatches
      ? [{ key: "__auto__", label: autoLabel, value: null }]
      : [];
    for (const zone of zones) {
      list.push({ key: zone, label: zone, value: zone });
    }
    return list;
  }, [query, t]);

  // The highlight always returns to the first candidate whenever the
  // candidate list itself changes — not only when its length changes,
  // so retyping into a same-sized but different list cannot leave the
  // highlight on a row the user never meant (t053_code_f003).
  useEffect(() => {
    setActiveIndex(0);
  }, [options]);

  useEffect(() => {
    if (!open) return;
    const active = document.getElementById(
      `${listboxId}-option-${activeIndex}`,
    );
    active?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, open, listboxId]);

  const select = (option: Option) => {
    onValueChange(option.value);
    setQuery(option.value ?? "");
    setOpen(false);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      setActiveIndex((prev) => Math.min(prev + 1, options.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      setActiveIndex((prev) => Math.max(prev - 1, 0));
    } else if (event.key === "Enter") {
      if (open && options[activeIndex]) {
        event.preventDefault();
        select(options[activeIndex]);
      }
    } else if (event.key === "Escape") {
      event.preventDefault();
      setQuery(value ?? "");
      setOpen(false);
    } else if (event.key === "Home" && open) {
      event.preventDefault();
      setActiveIndex(0);
    } else if (event.key === "End" && open) {
      event.preventDefault();
      setActiveIndex(options.length - 1);
    }
  };

  return (
    <div ref={wrapperRef} className="relative w-full">
      <input
        data-testid={testId}
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-controls={listboxId}
        aria-activedescendant={
          open ? `${listboxId}-option-${activeIndex}` : undefined
        }
        aria-autocomplete="list"
        autoComplete="off"
        className="h-(--component-input-height) w-full rounded-md border border-outline bg-surface px-md font-ui text-body-md text-on-surface placeholder:text-on-surface-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-50"
        value={query}
        placeholder={t("formTimezoneAuto")}
        onFocus={() => {
          setQuery(value ?? "");
          setOpen(true);
        }}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onKeyDown={handleKeyDown}
        onBlur={(event) => {
          if (
            wrapperRef.current &&
            event.relatedTarget instanceof Node &&
            wrapperRef.current.contains(event.relatedTarget)
          ) {
            return;
          }
          setOpen(false);
          setQuery(value ?? "");
        }}
      />
      {open && (
        <div
          id={listboxId}
          role="listbox"
          data-testid={testId ? `${testId}-listbox` : undefined}
          className="absolute z-50 mt-sm max-h-dropdown-list w-full overflow-y-auto rounded-lg border border-outline bg-surface-raised text-on-surface shadow-lg"
        >
          {options.length === 0 ? (
            <div className="px-md py-sm font-ui text-body-md text-on-surface-muted">
              {t("formTimezoneNoMatch")}
            </div>
          ) : (
            options.map((option, index) => (
              <div
                key={option.key}
                id={`${listboxId}-option-${index}`}
                role="option"
                aria-selected={index === activeIndex}
                data-testid={
                  testId ? `${testId}-option-${option.key}` : undefined
                }
                className={cn(
                  "cursor-default select-none px-md py-sm font-ui text-body-md",
                  index === activeIndex && "bg-surface-hover",
                )}
                onMouseDown={(event) => {
                  event.preventDefault();
                  select(option);
                }}
                onMouseEnter={() => setActiveIndex(index)}
              >
                {option.label}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
