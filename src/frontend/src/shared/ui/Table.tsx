import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";
import { cn } from "./cn";

export function Table({
  children,
  className,
  ...rest
}: HTMLAttributes<HTMLTableElement>) {
  return (
    <table
      className={cn("w-full border-collapse rounded-lg bg-surface text-on-surface", className)}
      {...rest}
    >
      {children}
    </table>
  );
}

export function TableHeader({
  children,
  className,
  ...rest
}: HTMLAttributes<HTMLTableSectionElement>) {
  return (
    <thead className={cn("bg-surface-subtle", className)} {...rest}>
      {children}
    </thead>
  );
}

export function TableBody({
  children,
  className,
  ...rest
}: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className={cn(className)} {...rest}>{children}</tbody>;
}

export function TableHead({
  children,
  className,
  ...rest
}: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className={cn(
        "px-md py-sm text-left font-mono text-mono-caps uppercase text-on-surface-muted",
        className,
      )}
      {...rest}
    >
      {children}
    </th>
  );
}

export function TableRow({
  children,
  selected,
  className,
  ...rest
}: HTMLAttributes<HTMLTableRowElement> & { selected?: boolean }) {
  return (
    <tr
      className={cn(
        "h-14 border-b border-outline hover:bg-surface-hover",
        selected && "bg-accent-soft",
        className,
      )}
      {...rest}
    >
      {children}
    </tr>
  );
}

export function TableCell({
  children,
  className,
  ...rest
}: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={cn("px-md py-sm font-ui text-body-sm", className)} {...rest}>
      {children}
    </td>
  );
}

export function MonoValue({ children }: { children: ReactNode }) {
  return <span className="font-mono text-mono-md">{children}</span>;
}
