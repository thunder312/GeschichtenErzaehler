import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-neutral-200 bg-white p-4 dark:border-neutral-800 dark:bg-neutral-900 ${className}`}>
      {children}
    </div>
  );
}

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const basis = "rounded-md px-3.5 py-1.5 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
  const varianten = {
    primary: "bg-purple-600 text-white hover:bg-purple-700",
    secondary: "border border-neutral-300 text-neutral-700 hover:bg-neutral-100 dark:border-neutral-700 dark:text-neutral-200 dark:hover:bg-neutral-800",
    danger: "bg-red-600 text-white hover:bg-red-700",
  };
  return <button className={`${basis} ${varianten[variant]} ${className}`} {...props} />;
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm text-neutral-900 outline-none focus:border-purple-500 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100 ${props.className ?? ""}`}
    />
  );
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={`w-full rounded-md border border-neutral-300 bg-white px-3 py-1.5 text-sm text-neutral-900 outline-none focus:border-purple-500 dark:border-neutral-700 dark:bg-neutral-950 dark:text-neutral-100 ${props.className ?? ""}`}
    />
  );
}

export function Label({ children }: { children: ReactNode }) {
  return <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-neutral-500">{children}</label>;
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "green" | "amber" }) {
  const toene = {
    neutral: "bg-neutral-100 text-neutral-700 dark:bg-neutral-800 dark:text-neutral-300",
    green: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
    amber: "bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300",
  };
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${toene[tone]}`}>{children}</span>;
}
