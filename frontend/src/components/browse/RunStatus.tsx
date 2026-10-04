"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { IconRefresh } from "@/components/ui/icons";
import { Timestamp } from "@/components/ui/Timestamp";
import { api, ApiError } from "@/lib/api";
import { humanize, pluralize } from "@/lib/format";
import { RUN_STATUS_LABEL, type Tone } from "@/lib/presentation";
import type { RunInfo, RunStatus as RunStatusValue } from "@/lib/types";

const POLL_INTERVAL_MS = 3000;

const RUN_STATUS_TONE: Record<RunStatusValue, Tone> = {
  running: "info",
  completed: "positive",
  completed_with_limitations: "warning",
  failed: "danger",
};

function describeError(error: unknown): string {
  if (error instanceof ApiError && error.isUnreachable) return "Can't reach the backend API. Is it running?";
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

export function RunStatus({ initialRun }: { initialRun: RunInfo | null }) {
  const router = useRouter();
  const [polledRun, setPolledRun] = useState<RunInfo | null>(null);
  const [pendingRunId, setPendingRunId] = useState<number | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = polledRun && (!initialRun || polledRun.id >= initialRun.id) ? polledRun : initialRun;
  const awaitingStart = pendingRunId !== null && (run === null || run.id < pendingRunId);
  const isRunning = awaitingStart || run?.status === "running";

  useEffect(() => {
    if (!isRunning) return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await api.getLatestRun();
        setPolledRun(latest);
        setError(null);
        const finished = latest !== null && latest.status !== "running" && (pendingRunId === null || latest.id >= pendingRunId);
        if (finished) {
          setPendingRunId(null);
          router.refresh();
        }
      } catch (pollError) {
        setError(describeError(pollError));
      }
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [isRunning, pendingRunId, router]);

  async function startRefresh() {
    setStarting(true);
    setError(null);
    try {
      const { run_id } = await api.startRun();
      setPendingRunId(run_id);
    } catch (startError) {
      if (startError instanceof ApiError && startError.status === 409) {
        setPolledRun(await api.getLatestRun().catch(() => null));
      } else {
        setError(describeError(startError));
      }
    } finally {
      setStarting(false);
    }
  }

  const busy = starting || isRunning;

  return (
    <div className="flex w-full flex-col gap-2 sm:w-auto sm:items-end">
      <div className="flex flex-wrap items-center gap-3 sm:justify-end">
        <p aria-live="polite" className="text-sm text-ink-muted">
          {isRunning ? (
            <span className="inline-flex items-center gap-2 font-medium text-ink">
              <span className="size-2 animate-pulse rounded-full bg-sky-500" aria-hidden="true" />
              Refreshing data…
              {run?.status === "running" && (
                <span className="font-normal text-ink-muted">
                  started <Timestamp iso={run.started_at} />
                </span>
              )}
            </span>
          ) : run ? (
            <span className="inline-flex flex-wrap items-center gap-2">
              <span>
                Last refresh: <Timestamp iso={run.finished_at ?? run.started_at} className="font-medium text-ink" />
              </span>
              <Badge tone={RUN_STATUS_TONE[run.status]}>{RUN_STATUS_LABEL[run.status]}</Badge>
            </span>
          ) : (
            "No data refresh has run yet"
          )}
        </p>
        <button
          type="button"
          onClick={startRefresh}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-xl border border-line-strong bg-surface px-3.5 py-2 text-sm font-semibold text-ink shadow-sm transition hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          <IconRefresh className={busy ? "animate-spin" : undefined} />
          {busy ? "Refreshing…" : "Refresh data"}
        </button>
      </div>
      {error && (
        <p role="alert" className="text-sm font-medium text-rose-700 dark:text-rose-300">
          {error}
        </p>
      )}
      {run && !isRunning && (run.limitations.length > 0 || Object.keys(run.stats).length > 0) && <RunDetails run={run} />}
    </div>
  );
}

function RunDetails({ run }: { run: RunInfo }) {
  const stats = Object.entries(run.stats);
  return (
    <details className="group/run w-full text-sm sm:max-w-md">
      <summary className="rounded text-ink-muted hover:text-ink focus-visible:outline-2 focus-visible:outline-accent sm:text-right">
        Run #{run.id} details
        {run.limitations.length > 0 && ` · ${pluralize(run.limitations.length, "limitation")}`}
        <span aria-hidden="true" className="ml-1 inline-block transition group-open/run:rotate-180">
          ▾
        </span>
      </summary>
      <div className="mt-2 space-y-3 rounded-xl border border-line bg-surface p-3 text-left">
        <p className="text-xs text-ink-faint">
          Started <Timestamp iso={run.started_at} />
          {run.finished_at && (
            <>
              {" "}
              · Finished <Timestamp iso={run.finished_at} />
            </>
          )}
        </p>
        {stats.length > 0 && (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
            {stats.map(([key, value]) => (
              <div key={key} className="flex justify-between gap-2">
                <dt className="text-ink-muted">{humanize(key)}</dt>
                <dd className="font-medium tabular-nums text-ink">{value.toLocaleString("en-US")}</dd>
              </div>
            ))}
          </dl>
        )}
        {run.limitations.length > 0 && (
          <div>
            <p className="mb-1 font-medium text-ink">Source limitations</p>
            <ul className="space-y-1 text-ink-muted">
              {run.limitations.map((limitation, index) => (
                <li key={`${limitation.source_id}-${index}`}>
                  <span className="font-medium text-ink">{limitation.source_id}:</span> {limitation.message}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </details>
  );
}
