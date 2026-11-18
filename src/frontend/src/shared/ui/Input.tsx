import type { InputHTMLAttributes, ReactNode, Ref } from "react";
import { Search } from "lucide-react";
import { cn } from "./cn";

const FIELD =
  "h-(--component-input-height) w-full rounded-md border border-outline bg-surface px-md font-ui text-body-md text-on-surface placeholder:text-on-surface-subtle focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:opacity-50";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export function Input({ label, className, id, ...rest }: InputProps) {
  return (
    <input
      id={id}
      aria-label={label}
      className={cn(FIELD, className)}
      {...rest}
    />
  );
}

export interface SearchFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  containerClassName?: string;
  ref?: Ref<HTMLInputElement>;
}

export function SearchField({
  label,
  className,
  containerClassName,
  ref,
  ...rest
}: SearchFieldProps) {
  return (
    <div
      className={cn(
        "flex h-(--component-input-height) items-center gap-sm rounded-md border border-outline bg-surface px-md transition-colors focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-focus",
        containerClassName,
      )}
    >
      <Search
        aria-hidden="true"
        className="size-(--component-icon-md-size) shrink-0 text-on-surface-muted"
      />
      <input
        ref={ref}
        aria-label={label}
        type="search"
        className={cn(
          "flex-1 overflow-hidden bg-transparent font-ui text-body-md text-on-surface placeholder:text-on-surface-subtle focus:outline-none disabled:opacity-50",
          className,
        )}
        {...rest}
      />
    </div>
  );
}

export function FieldLabel({
  htmlFor,
  children,
}: {
  htmlFor?: string;
  children: ReactNode;
}) {
  return (
    <label
      htmlFor={htmlFor}
      className="block font-ui text-label-sm text-on-surface-muted"
    >
      {children}
    </label>
  );
}
