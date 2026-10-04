import type { ReactNode } from "react";
import { IconAlert, IconInfo } from "./icons";

interface StateMessageProps {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  tone?: "neutral" | "error";
}

export function StateMessage({ title, children, action, tone = "neutral" }: StateMessageProps) {
  const Icon = tone === "error" ? IconAlert : IconInfo;
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className="mx-auto flex max-w-xl flex-col items-center rounded-3xl border border-dashed border-line-strong bg-surface px-6 py-12 text-center"
    >
      <span
        className={`mb-4 grid size-12 place-items-center rounded-full text-2xl ${
          tone === "error"
            ? "bg-rose-50 text-rose-700 dark:bg-rose-400/10 dark:text-rose-300"
            : "bg-surface-muted text-ink-muted"
        }`}
      >
        <Icon />
      </span>
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
      {children && <div className="mt-2 space-y-2 text-sm text-ink-muted">{children}</div>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
