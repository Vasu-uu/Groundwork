import type { Evidence } from "../api/types";
import { useOpenSource } from "./SourcePanel";
import { cx } from "./ui";

/** A verified quote. Clicking it opens the transcript with the quote highlighted. */
export function QuoteCard({
  evidence,
  tone = "neutral",
  struck = false,
}: {
  evidence: Evidence;
  tone?: "neutral" | "for" | "against";
  struck?: boolean;
}) {
  const open = useOpenSource();
  const border = { neutral: "border-stone-300", for: "border-emerald-500", against: "border-rose-500" }[tone];
  return (
    <button
      type="button"
      onClick={() => open(evidence)}
      className={cx(
        "group block w-full rounded-md border-l-4 bg-stone-50 px-3 py-2 text-left transition hover:bg-stone-100",
        "focus-visible:outline-2 focus-visible:outline-brand-600",
        border,
        struck && "opacity-50",
      )}
      title="Show in transcript"
    >
      <q className={cx("font-serif text-[15px] leading-snug text-stone-800", struck && "line-through")}>
        {evidence.quote.replace(/\s+/g, " ")}
      </q>
      <span className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-stone-500">
        <span className="font-medium text-stone-600">{evidence.speaker}</span>
        <span>
          {evidence.interview_id} · S{evidence.segment}
        </span>
        {evidence.paraphrase && <span className="text-amber-700">paraphrase (notes)</span>}
        {evidence.match === "fuzzy" && <span>fuzzy {Math.round(evidence.score * 100)}%</span>}
        <span className="ml-auto text-brand-700 opacity-0 transition group-hover:opacity-100">
          view source →
        </span>
      </span>
    </button>
  );
}
