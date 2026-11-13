import type { InputHTMLAttributes, ReactNode } from "react";
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
}

export function SearchField({
  label,
  className,
  containerClassName,
  ...rest
}: SearchFieldProps) {
  return (
    <div className={cn("relative", containerClassName)}>
      <Search
        aria-hidden="true"
        className="pointer-events-none absolute left-md top-1/2 size-(--component-icon-md-size) -translate-y-1/2 text-on-surface-muted"
      />
      <Input
        label={label}
        type="search"
        className={cn("pl-xl", className)}
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
      className="mb-sm block font-ui text-label-sm text-on-surface-muted"
    >
      {children}
    </label>
  );
}
