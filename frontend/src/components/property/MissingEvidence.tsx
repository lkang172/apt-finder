"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { EvidenceItem } from "@/lib/types";
import { EvidenceCard } from "./EvidenceCard";

type LoadState = { status: "idle" | "loading" } | { status: "error"; message: string } | { status: "loaded"; item: EvidenceItem };

export function MissingEvidence({ id, officialUrl }: { id: string; officialUrl: string | null }) {
  const [state, setState] = useState<LoadState>({ status: "idle" });

  if (state.status === "loaded") return <EvidenceCard item={state.item} officialUrl={officialUrl} />;

  async function load() {
    setState({ status: "loading" });
    try {
      setState({ status: "loaded", item: await api.getEvidence(id) });
    } catch (error) {
      setState({ status: "error", message: error instanceof Error ? error.message : "Couldn't load this evidence." });
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-xl border border-dashed border-line-strong px-3 py-2 text-sm text-ink-muted">
      <span>Evidence {id} isn&apos;t included in this page.</span>
      <button
        type="button"
        onClick={load}
        disabled={state.status === "loading"}
        className="rounded-lg px-2 py-1 font-medium text-accent hover:bg-accent-soft disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-accent"
      >
        {state.status === "loading" ? "Loading…" : "Load evidence"}
      </button>
      {state.status === "error" && (
        <span role="alert" className="text-rose-700 dark:text-rose-300">
          {state.message}
        </span>
      )}
    </div>
  );
}
