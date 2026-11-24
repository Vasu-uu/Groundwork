import { useState } from "react";
import type { Evidence, HypothesisVerdict } from "../api/types";
import { CONFIDENCE_LABEL, STANCE_LABEL } from "../lib/labels";
import { QuoteCard } from "./QuoteCard";
import { Card, Pill, VerdictBadge, cx } from "./ui";

const PREVIEW = 3;

/** Segmented bar: how interviewees split on this hypothesis. */
export function StanceBar({ v }: { v: HypothesisVerdict }) {
  const c = v.counts;
  const total = c.supports + c.contradicts + c.mixed + c.not_discussed || 1;
  const parts = [
    { n: c.supports, label: "support", cls: "bg-emerald-500" },
    { n: c.mixed, label: "mixed", cls: "bg-amber-400" },
    { n: c.contradicts, label: "contradict", cls: "bg-rose-500" },
    { n: c.not_discussed, label: "did not discuss", cls: "bg-stone-200" },
  ];
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full bg-stone-100" aria-hidden>
        {parts.map((p) => (
          <span key={p.label} className={p.cls} style={{ width: `${(p.n / total) * 100}%` }} />
        ))}
      </div>
      <p className="mt-1.5 flex flex-wrap gap-x-3 text-xs text-stone-600">
        {parts.map((p) => (
          <span key={p.label} className="flex items-center gap-1">
            <span className={cx("size-2 rounded-full", p.cls)} />
            {p.n} {p.label}
          </span>
        ))}
      </p>
    </div>
  );
}

function QuoteColumn({
  title,
  items,
  tone,
  empty,
  removed,
}: {
  title: string;
  items: Evidence[];
  tone: "for" | "against";
  empty: string;
  removed?: Set<string>;
}) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, PREVIEW);
  return (
    <div>
      <h4
        className={cx(
          "mb-2 text-xs font-semibold uppercase tracking-wide",
          tone === "for" ? "text-emerald-700" : "text-rose-700",
        )}
      >
        {title} ({items.length})
      </h4>
      {items.length === 0 ? (
        <p className="rounded-md bg-stone-50 px-3 py-2 text-sm text-stone-500">{empty}</p>
      ) : (
        <div className="space-y-2">
          {shown.map((e) => (
            <QuoteCard key={e.key} evidence={e} tone={tone} struck={removed?.has(e.key)} />
          ))}
          {items.length > PREVIEW && (
            <button type="button" onClick={() => setAll(!all)} className="text-xs font-medium text-brand-700 hover:underline">
              {all ? "Show fewer" : `Show all ${items.length}`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/** One hypothesis with its AI-suggested verdict and the evidence on both sides. */
export function HypothesisCard({
  v,
  devilsAdvocate,
  removed,
}: {
  v: HypothesisVerdict;
  devilsAdvocate: boolean;
  removed?: Set<string>;
}) {
  const discussed = v.assessments.filter((a) => a.stance !== "not_discussed");
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-stone-400">{v.hypothesis.id}</p>
          <h3 className="text-base font-semibold leading-snug text-stone-900">{v.hypothesis.text}</h3>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-stone-500">AI suggestion</span>
          <VerdictBadge verdict={v.verdict} />
          <span className="text-xs text-stone-600">{CONFIDENCE_LABEL[v.confidence]}</span>
        </div>
      </div>

      <div className="mt-4">
        <StanceBar v={v} />
      </div>
      <p className="mt-3 text-sm text-stone-700">{v.confidence_note}</p>
      {v.provisional && (
        <p className="mt-1 text-xs font-medium text-amber-800">Provisional: fewer than 5 interviews.</p>
      )}

      {devilsAdvocate && (
        <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50/60 p-3">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-rose-800">
            Devil's advocate: strongest evidence against
          </h4>
          {v.counter_evidence.length ? (
            <div className="mt-2 space-y-2">
              {v.counter_evidence.slice(0, PREVIEW).map((e) => (
                <QuoteCard key={e.key} evidence={e} tone="against" />
              ))}
            </div>
          ) : (
            <p className="mt-1 text-sm text-rose-900">
              No interviewee contradicted it. That is not proof: {v.counts.not_discussed} of{" "}
              {v.counts.supports + v.counts.contradicts + v.counts.mixed + v.counts.not_discussed}{" "}
              never discussed it, and people rarely volunteer disagreement. Ask about it directly.
            </p>
          )}
        </div>
      )}

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <QuoteColumn title="Supporting" items={v.supporting} tone="for" empty="No supporting quotes." removed={removed} />
        <QuoteColumn
          title="Contradicting"
          items={v.contradicting}
          tone="against"
          empty="No contradicting quotes."
          removed={removed}
        />
      </div>

      <div className="mt-4 rounded-lg bg-stone-50 px-3 py-2.5 text-sm">
        <span className="font-medium text-stone-800">What would change this verdict: </span>
        <span className="text-stone-700">{v.what_would_change}</span>
      </div>

      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-xs font-medium text-stone-500 hover:text-stone-800">
          How this was decided ({discussed.length} interviews discussed it)
        </summary>
        <p className="mt-2 text-xs text-stone-600">{v.rule}</p>
        <table className="mt-2 w-full text-left text-xs">
          <thead className="text-stone-500">
            <tr>
              <th className="py-1 pr-2 font-medium">Interview</th>
              <th className="py-1 pr-2 font-medium">Stance</th>
              <th className="py-1 font-medium">Model's rationale</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100 text-stone-700">
            {v.assessments.map((a) => (
              <tr key={a.interview_id}>
                <td className="py-1 pr-2 font-medium">{a.interview_id}</td>
                <td className="py-1 pr-2">
                  {STANCE_LABEL[a.stance]}
                  {a.downgraded_from && (
                    <span title="The model claimed this, but none of its quotes could be verified" className="ml-1 text-amber-700">
                      (claimed {STANCE_LABEL[a.downgraded_from]})
                    </span>
                  )}
                </td>
                <td className="py-1">{a.rationale || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {v.related_theme_ids.length > 0 && (
          <p className="mt-2 text-xs text-stone-500">
            Related pain themes: {v.related_theme_ids.map((t) => <Pill key={t}>{t}</Pill>)}
          </p>
        )}
      </details>
    </Card>
  );
}
