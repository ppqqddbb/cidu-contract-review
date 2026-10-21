import type { ReactNode } from "react";

import { cn } from "../../lib/cn";

interface AppShellProps {
  title: string;
  eyebrow: string;
  version: string;
  statusLabel: string;
  statusTone: "success" | "warning" | "error";
  navigationAction?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}

const statusDotClass = {
  success: "status-dot-success",
  warning: "status-dot-warning",
  error: "status-dot-error",
} as const;

export function AppShell({
  title,
  eyebrow,
  version,
  statusLabel,
  statusTone,
  navigationAction,
  actions,
  children,
}: AppShellProps) {
  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <section className="min-w-0">
        <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 backdrop-blur">
          <div className="flex min-h-14 items-center justify-between gap-3 px-4 py-2 lg:px-6">
            <div className="flex min-w-0 items-center gap-3">
              {navigationAction && (
                <div className="shrink-0">{navigationAction}</div>
              )}
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                    {eyebrow}
                  </p>
                  <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold text-slate-500">
                    {version}
                  </span>
                </div>
                <h1 className="truncate text-base font-bold tracking-tight text-slate-950 sm:text-lg">
                  {title}
                </h1>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <div className="hidden items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-[11px] font-medium text-slate-600 sm:flex">
                <span
                  className={cn("status-dot", statusDotClass[statusTone])}
                />
                {statusLabel}
              </div>
              {actions}
            </div>
          </div>
        </header>

        <div className="space-y-4 px-4 py-4 lg:px-6">{children}</div>
      </section>
    </main>
  );
}
