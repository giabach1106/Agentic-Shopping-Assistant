"use client";

import { AlertTriangle, CheckCircle2, LoaderCircle, ShieldAlert } from "lucide-react";

import type { TraceEvent } from "@/lib/contracts";

function statusMeta(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "ok") {
    return {
      icon: <CheckCircle2 className="h-4 w-4" />,
      className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    };
  }
  if (normalized === "warning" || normalized === "need_data") {
    return {
      icon: <AlertTriangle className="h-4 w-4" />,
      className: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
    };
  }
  if (normalized === "blocked" || normalized === "error") {
    return {
      icon: <ShieldAlert className="h-4 w-4" />,
      className: "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300",
    };
  }
  return {
    icon: <LoaderCircle className="h-4 w-4" />,
    className: "border-[color:var(--border)] bg-[color:var(--surface-muted)] text-[color:var(--text-strong)]",
  };
}

export function TracePanel({ trace }: { trace: TraceEvent[] }) {
  if (!trace.length) {
    return null;
  }

  return (
    <section className="rounded-[2rem] border border-[color:var(--border)] bg-[color:var(--surface)] p-6 shadow-[var(--shadow-soft)]">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-[color:var(--text-muted)]">Agent trace</p>
          <h2 className="text-xl font-semibold text-[color:var(--text-strong)]">Structured reasoning timeline</h2>
        </div>
        <span className="rounded-full border border-[color:var(--border)] px-3 py-1 text-xs text-[color:var(--text-muted)]">
          {trace.length} steps
        </span>
      </div>

      <div className="space-y-4">
        {trace.map((event, index) => {
          const meta = statusMeta(event.status);
          return (
            <div key={`${event.agent ?? "agent"}-${event.step}-${index}`} className="grid grid-cols-[auto_1fr] gap-4">
              <div className={`mt-1 flex h-9 w-9 items-center justify-center rounded-2xl border ${meta.className}`}>
                {meta.icon}
              </div>
              <div className="rounded-[1.6rem] border border-[color:var(--border)] bg-[color:var(--surface-muted)] p-4">
                <div className="mb-1 flex items-center gap-2">
                  <span className="text-sm font-semibold capitalize text-[color:var(--text-strong)]">
                    {event.agent ?? "agent"}
                  </span>
                  <span className="text-xs uppercase tracking-[0.2em] text-[color:var(--text-muted)]">
                    {event.step.replaceAll("_", " ")}
                  </span>
                </div>
                <p className="text-sm leading-6 text-[color:var(--text-soft)]">
                  {event.detail || "Completed without additional detail."}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
