import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { Verdict } from "../api/types";
import { VERDICT_HELP, VERDICT_STYLE } from "../lib/labels";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANT: Record<Variant, string> = {
  primary:
    "bg-brand-800 text-white hover:bg-brand-900 disabled:bg-stone-300 disabled:text-stone-500",
  secondary:
    "bg-white text-stone-800 ring-1 ring-stone-300 hover:bg-stone-50 disabled:text-stone-400",
  ghost: "text-stone-600 hover:bg-stone-100 hover:text-stone-900 disabled:text-stone-400",
  danger: "bg-white text-rose-700 ring-1 ring-rose-200 hover:bg-rose-50",
};

export function Button({
  variant = "primary",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600",
        "disabled:cursor-not-allowed",
        VARIANT[variant],
        className,
      )}
      {...props}
    />
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-xl border border-stone-200 bg-white shadow-sm", className)}>
      {children}
    </section>
  );
}

export function VerdictBadge({ verdict, size = "md" }: { verdict: Verdict; size?: "sm" | "md" }) {
  return (
    <span
      title={VERDICT_HELP[verdict]}
      className={cx(
        "inline-flex items-center rounded-md font-semibold tracking-wide ring-1 ring-inset",
        size === "sm" ? "px-1.5 py-0.5 text-[11px]" : "px-2 py-1 text-xs",
        VERDICT_STYLE[verdict],
      )}
    >
      {verdict}
    </span>
  );
}

export function Pill({ children, tone = "stone" }: { children: ReactNode; tone?: "stone" | "amber" | "brand" | "rose" }) {
  const tones = {
    stone: "bg-stone-100 text-stone-700",
    amber: "bg-amber-100 text-amber-900",
    brand: "bg-brand-50 text-brand-800",
    rose: "bg-rose-50 text-rose-800",
  };
  return (
    <span className={cx("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", tones[tone])}>
      {children}
    </span>
  );
}

export function Banner({
  tone = "amber",
  title,
  children,
}: {
  tone?: "amber" | "rose" | "brand" | "stone";
  title?: ReactNode;
  children?: ReactNode;
}) {
  const tones = {
    amber: "border-amber-200 bg-amber-50 text-amber-950",
    rose: "border-rose-200 bg-rose-50 text-rose-950",
    brand: "border-brand-100 bg-brand-50 text-brand-900",
    stone: "border-stone-200 bg-stone-100 text-stone-800",
  };
  return (
    <div role={tone === "rose" ? "alert" : "status"} className={cx("rounded-lg border px-4 py-3 text-sm", tones[tone])}>
      {title && <p className="font-semibold">{title}</p>}
      {children && <div className={cx(title ? "mt-1" : null, "space-y-1")}>{children}</div>}
    </div>
  );
}

export function SectionTitle({ title, subtitle, right }: { title: string; subtitle?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="text-lg font-semibold text-stone-900">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-stone-600">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export function Spinner() {
  return (
    <span
      aria-hidden
      className="inline-block size-4 animate-spin rounded-full border-2 border-current border-r-transparent"
    />
  );
}
