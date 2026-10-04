import type { ReactNode } from "react";

interface SectionProps {
  id: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}

export function Section({ id, title, description, actions, children }: SectionProps) {
  const headingId = `${id}-heading`;
  return (
    <section id={id} aria-labelledby={headingId} className="scroll-mt-28">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id={headingId} className="text-xl font-semibold tracking-tight text-ink">
            {title}
          </h2>
          {description && <p className="mt-1 text-sm text-ink-muted">{description}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

interface CardProps {
  children: ReactNode;
  className?: string;
  flush?: boolean;
}

export function Card({ children, className = "", flush = false }: CardProps) {
  return (
    <div className={`rounded-2xl border border-line bg-surface shadow-sm ${flush ? "" : "p-5"} ${className}`}>{children}</div>
  );
}
