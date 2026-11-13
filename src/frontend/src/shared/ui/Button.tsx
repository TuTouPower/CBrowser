import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "ghost"
  | "danger"
  | "connect"
  | "stop";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-accent text-on-accent",
  secondary: "bg-surface-subtle text-on-surface border border-outline",
  ghost: "bg-surface text-on-surface",
  danger: "bg-danger text-on-accent",
  connect: "bg-accent text-on-accent",
  stop: "bg-danger text-on-accent",
};

const FOCUS =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "md" | "sm";
  children: ReactNode;
}

export function Button({
  variant = "secondary",
  size = "md",
  type = "button",
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        "inline-flex items-center justify-center gap-sm rounded-md font-ui text-label-md transition-colors",
        size === "sm" ? "h-control-sm px-sm" : "h-(--component-button-primary-height) px-md",
        VARIANTS[variant],
        "disabled:cursor-not-allowed disabled:opacity-50",
        FOCUS,
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  children: ReactNode;
}

export function IconButton({
  label,
  type = "button",
  className,
  children,
  ...rest
}: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      className={cn(
        "inline-flex h-(--component-icon-button-height) w-(--component-icon-button-width) items-center justify-center rounded-md bg-surface text-on-surface hover:bg-surface-hover",
        FOCUS,
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}
