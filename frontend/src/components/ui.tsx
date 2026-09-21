import Link from "next/link";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

import { IconLoader } from "@/components/icons";

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

/* ---------------------------------------------------------------- Card */

export function Card({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx("card", className)} {...rest} />;
}

export function CardHeader({
  title,
  description,
  action,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("flex items-start justify-between gap-4 border-b border-border px-5 py-4", className)}>
      <div className="min-w-0">
        <h2 className="text-sm font-semibold text-fg">{title}</h2>
        {description ? <p className="mt-0.5 text-xs text-muted">{description}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

/* --------------------------------------------------------------- Badge */

export type Tone = "neutral" | "accent" | "success" | "warning" | "danger";

const BADGE_TONE: Record<Tone, string> = {
  neutral: "bg-surface-2 text-fg-2 border-border",
  accent: "bg-accent-soft text-accent border-transparent",
  success: "bg-success-soft text-success border-transparent",
  warning: "bg-warning-soft text-warning border-transparent",
  danger: "bg-danger-soft text-danger border-transparent",
};

export function Badge({
  tone = "neutral",
  dot = false,
  pulse = false,
  className,
  children,
}: {
  tone?: Tone;
  dot?: boolean;
  pulse?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium leading-5",
        BADGE_TONE[tone],
        className,
      )}
    >
      {dot ? <span className={cx("h-1.5 w-1.5 rounded-full bg-current", pulse && "pulse-dot")} /> : null}
      {children}
    </span>
  );
}

/* -------------------------------------------------------------- Button */

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-accent-fg shadow-[var(--shadow-glow)] hover:brightness-110 active:brightness-95 disabled:shadow-none",
  secondary: "bg-surface text-fg border border-border-strong hover:bg-surface-hover",
  ghost: "text-fg-2 hover:bg-surface-2 hover:text-fg",
  danger: "bg-danger text-white hover:brightness-110",
};

const BUTTON_SIZE: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-xs gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
  lg: "h-11 px-5 text-sm gap-2",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}) {
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center rounded-xl font-medium transition-[background-color,box-shadow,filter,transform] duration-150 disabled:opacity-60",
        BUTTON_VARIANT[variant],
        BUTTON_SIZE[size],
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <IconLoader size={16} /> : null}
      {children}
    </button>
  );
}

/* ---------------------------------------------------------------- Stat */

export function Stat({
  label,
  value,
  hint,
  icon,
  tone = "neutral",
  loading = false,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: Tone;
  loading?: boolean;
}) {
  const iconTone: Record<Tone, string> = {
    neutral: "bg-surface-2 text-fg-2",
    accent: "bg-accent-soft text-accent",
    success: "bg-success-soft text-success",
    warning: "bg-warning-soft text-warning",
    danger: "bg-danger-soft text-danger",
  };
  return (
    <Card className="card-interactive flex items-center gap-4 px-5 py-4">
      {icon ? (
        <div className={cx("flex h-10 w-10 shrink-0 items-center justify-center rounded-xl", iconTone[tone])}>
          {icon}
        </div>
      ) : null}
      <div className="min-w-0 flex-1">
        <div className="text-xs font-medium text-muted">{label}</div>
        {loading ? (
          <div className="skeleton mt-1.5 h-7 w-16" />
        ) : (
          <div className="tabular mt-0.5 text-2xl font-semibold tracking-tight text-fg">{value}</div>
        )}
        {hint ? <div className="mt-0.5 truncate text-[11px] text-muted-2">{hint}</div> : null}
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------ Skeleton */

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton", className)} aria-hidden="true" />;
}

/* ---------------------------------------------------------- EmptyState */

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      {icon ? (
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">
          {icon}
        </div>
      ) : null}
      <h3 className="text-sm font-semibold text-fg">{title}</h3>
      {description ? <p className="mt-1 max-w-sm text-sm text-muted">{description}</p> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

/* ---------------------------------------------------------- PageHeader */

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="fade-up flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
      <div className="min-w-0">
        {eyebrow ? <div className="eyebrow">{eyebrow}</div> : null}
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-fg md:text-4xl">{title}</h1>
        {description ? <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-3">{actions}</div> : null}
    </header>
  );
}

/* --------------------------------------------------------------- Alert */

export function Alert({
  tone = "danger",
  title,
  children,
  icon,
}: {
  tone?: Tone;
  title?: string;
  children: ReactNode;
  icon?: ReactNode;
}) {
  const tones: Record<Tone, string> = {
    neutral: "border-border bg-surface-2 text-fg-2",
    accent: "border-transparent bg-accent-soft text-accent",
    success: "border-transparent bg-success-soft text-success",
    warning: "border-transparent bg-warning-soft text-warning",
    danger: "border-transparent bg-danger-soft text-danger",
  };
  return (
    <div role="alert" className={cx("fade-up flex items-start gap-3 rounded-xl border px-4 py-3 text-sm", tones[tone])}>
      {icon ? <span className="mt-0.5 shrink-0">{icon}</span> : null}
      <div className="min-w-0">
        {title ? <div className="font-semibold">{title}</div> : null}
        <div className={title ? "mt-0.5 opacity-90" : ""}>{children}</div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------- TextLink */

export function TextLink({ href, children, className }: { href: string; children: ReactNode; className?: string }) {
  return (
    <Link href={href} className={cx("font-medium text-accent hover:underline underline-offset-4", className)}>
      {children}
    </Link>
  );
}

export { cx };
