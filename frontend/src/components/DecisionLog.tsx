import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { LogEntry } from "../api/types";
import { Card, Pill } from "./ui";

const ACTION_LABEL: Record<string, string> = {
  study_created: "Study created",
  interviews_added: "Interviews added",
  interview_removed: "Interview removed",
  hypotheses_updated: "Hypotheses updated",
  analysis_started: "Analysis started",
  analysis_completed: "Analysis completed",
  analysis_failed: "Analysis failed",
  analysis_reset: "Previous analysis discarded",
  review_saved: "Verdict reviewed",
  approved: "Checkpoint approved",
  reviews_cleared: "Earlier reviews cleared",
  reopened: "Review reopened",
};

const ACTOR_TONE = { founder: "brand", ai: "amber", system: "stone" } as const;

/** One-line human summary of a log entry's details. */
export function describe(e: LogEntry): string {
  const d = e.details;
  if (e.action === "review_saved") {
    const after = d.after as { decision?: string; final_verdict?: string | null; reasoning?: string } | null;
    if (!after) return "";
    const verdict = after.final_verdict ?? "re-test";
    const why = after.reasoning ? `: “${after.reasoning}”` : "";
    return `${after.decision} (AI said ${String(d.ai_suggestion)}, final ${verdict})${why}`;
  }
  if (e.action === "approved" && d.final_verdicts && typeof d.final_verdicts === "object") {
    return Object.entries(d.final_verdicts as Record<string, string | null>)
      .map(([h, v]) => `${h} ${v ?? "re-test"}`)
      .join(" · ");
  }
  if (e.action === "analysis_completed") {
    const s = d.suggestions as Record<string, string> | undefined;
    const parts = [`${String(d.pain_points)} pain points`, `${String(d.verified_quotes)}`];
    if (s) parts.push(Object.entries(s).map(([h, v]) => `${h} ${v}`).join(" · "));
    return parts.join(", ");
  }
  if (typeof d.reason === "string" && d.reason) return d.reason;
  if (typeof d.error === "string") return d.error;
  if (Array.isArray(d.interviews)) return (d.interviews as { id: string }[]).map((i) => i.id).join(", ");
  if (typeof d.interview_id === "string") return d.interview_id;
  return "";
}

/** Append-only audit trail of every decision, with timestamps. */
export function DecisionLog({ studyId, version }: { studyId: string; version: string }) {
  const [entries, setEntries] = useState<LogEntry[] | null>(null);

  useEffect(() => {
    api.decisionLog(studyId).then(setEntries).catch(() => setEntries([]));
  }, [studyId, version]);

  if (!entries) return null;
  return (
    <Card className="p-5">
      <h3 className="font-semibold text-stone-900">Decision log</h3>
      <p className="mt-0.5 text-sm text-stone-600">Every edit is recorded with a timestamp and cannot be deleted.</p>
      <ol className="mt-4 space-y-2 text-sm">
        {[...entries].reverse().map((e) => (
          <li key={e.id} className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-l-2 border-stone-200 pl-3">
            <time className="w-36 shrink-0 text-xs tabular-nums text-stone-500" dateTime={e.at}>
              {new Date(e.at).toLocaleString()}
            </time>
            <Pill tone={ACTOR_TONE[e.actor]}>{e.actor}</Pill>
            <span className="font-medium text-stone-800">
              {ACTION_LABEL[e.action] ?? e.action}
              {e.hypothesis_id && ` · ${e.hypothesis_id}`}
            </span>
            <span className="min-w-0 basis-full pl-38 text-stone-600 sm:basis-auto sm:pl-0">{describe(e)}</span>
          </li>
        ))}
      </ol>
    </Card>
  );
}
