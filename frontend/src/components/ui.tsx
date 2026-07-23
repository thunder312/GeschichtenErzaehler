import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-2xl border border-border bg-surface p-4 shadow-sm shadow-black/20 transition-colors ${className}`}
    >
      {children}
    </div>
  );
}

export function CardTitle({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <h2 className={`font-heading mb-3 text-lg font-semibold tracking-wide text-text ${className}`}>{children}</h2>;
}

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const basis =
    "rounded-full px-4 py-1.5 text-sm font-medium transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.97]";
  const varianten = {
    primary: "bg-accent text-[#0c1712] hover:bg-accent-hover hover:shadow-md hover:shadow-accent/20",
    secondary: "border border-border text-text hover:bg-surface-hover",
    danger: "bg-red-500/90 text-[#1a0505] hover:bg-red-500",
  };
  return <button className={`${basis} ${varianten[variant]} ${className}`} {...props} />;
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full rounded-lg border border-border bg-bg px-3 py-1.5 text-sm text-text outline-none transition-colors placeholder:text-text-muted/70 focus:border-accent ${props.className ?? ""}`}
    />
  );
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`w-full rounded-lg border border-border bg-bg px-3 py-1.5 text-sm text-text outline-none transition-colors focus:border-accent ${props.className ?? ""}`}
    />
  );
}

export function Label({ children }: { children: ReactNode }) {
  return <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-text-muted">{children}</label>;
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "green" | "amber" }) {
  const toene = {
    neutral: "bg-surface-hover text-text-muted",
    green: "bg-accent-soft text-accent-light",
    amber: "bg-amber-400/15 text-amber-300",
  };
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${toene[tone]}`}>{children}</span>;
}
