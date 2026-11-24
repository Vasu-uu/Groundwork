import { useMemo, useState } from "react";
import type { PainPoint, Study, Theme } from "../api/types";
import { HypothesisCard } from "../components/HypothesisCard";
import { QuoteCard } from "../components/QuoteCard";
import { Banner, Button, Card, Pill, SectionTitle, cx } from "../components/ui";

export function EvidenceStep({ study, goStep }: { study: Study; goStep: (n: number) => void }) {
  const result = study.result!;
  const [devil, setDevil] = useState(false);
  const byId = useMemo(() => new Map(result.pain_points.map((p) => [p.id, p])), [result]);
  const stats = result.quote_stats;

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="Interviews" value={result.interview_count} />
        <Metric label="Verified pain points" value={result.pain_points.length} />
        <Metric label="Pain themes" value={result.clustering.themes.length} />
        <Metric
          label="Verified quotes"
          value={`${stats.verified}/${stats.proposed}`}
          hint={`${stats.rejected} quote(s) the model proposed could not be found in the transcripts and are never shown as evidence.`}
        />
      </div>

      {result.warnings.length > 0 && (
        <Banner title="Read these results with care">
          {result.warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </Banner>
      )}

      <section>
        <SectionTitle
          title="Hypotheses"
          subtitle="Verdicts are AI suggestions computed from verified quotes. You decide on the next step."
          right={
            <div className="flex items-center gap-2 text-sm font-medium text-stone-700">
              <span id="devil-label" title="Show the strongest evidence against each hypothesis">
                Devil's advocate
              </span>
              <button
                type="button"
                role="switch"
                aria-labelledby="devil-label"
                aria-checked={devil}
                onClick={() => setDevil(!devil)}
                className={cx(
                  "relative h-6 w-11 rounded-full transition",
                  devil ? "bg-rose-600" : "bg-stone-300",
                )}
              >
                <span
                  className={cx(
                    "absolute top-0.5 size-5 rounded-full bg-white shadow transition",
                    devil ? "left-5.5" : "left-0.5",
                  )}
                />
              </button>
            </div>
          }
        />
        <div className="space-y-4">
          {result.verdicts.map((v) => (
            <HypothesisCard key={v.hypothesis.id} v={v} devilsAdvocate={devil} />
          ))}
        </div>
      </section>

      <section>
        <SectionTitle
          title="Pain themes"
          subtitle={
            <>
              Ranked by how many different interviewees mentioned them.
              {result.clustering.method === "fallback" && " Grouped by keyword overlap because the model failed."}
            </>
          }
        />
        <div className="grid gap-4 md:grid-cols-2">
          {result.clustering.themes.map((t) => (
            <ThemeCard key={t.id} theme={t} points={t.pain_point_ids.flatMap((id) => byId.get(id) ?? [])} total={result.interview_count} />
          ))}
        </div>
        {result.clustering.themes.length === 0 && (
          <p className="text-sm text-stone-500">No verified pain points were found.</p>
        )}
      </section>

      <section className="space-y-2">
        {result.clustering.unclustered.length > 0 && (
          <details className="rounded-lg border border-stone-200 bg-white p-4">
            <summary className="cursor-pointer text-sm font-medium text-stone-700">
              Pain points outside any theme ({result.clustering.unclustered.length})
            </summary>
            <div className="mt-3 space-y-2">
              {result.clustering.unclustered.flatMap((id) => byId.get(id) ?? []).map((p) => (
                <div key={p.id}>
                  <p className="mb-1 text-sm text-stone-700">{p.summary}</p>
                  <QuoteCard evidence={p.evidence} />
                </div>
              ))}
            </div>
          </details>
        )}
        {result.rejected_quotes.length > 0 && (
          <details className="rounded-lg border border-stone-200 bg-white p-4">
            <summary className="cursor-pointer text-sm font-medium text-stone-700">
              Quotes rejected by verification ({result.rejected_quotes.length}): never used as evidence
            </summary>
            <ul className="mt-3 space-y-2 text-sm">
              {result.rejected_quotes.map((r, i) => (
                <li key={i} className="rounded-md bg-stone-50 px-3 py-2">
                  <q className="text-stone-500 line-through">{r.quote}</q>
                  <p className="mt-0.5 text-xs text-stone-600">
                    {r.interview_id}: {r.reason}
                  </p>
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>

      <div className="flex justify-end">
        <Button onClick={() => goStep(3)}>Review the verdicts →</Button>
      </div>
    </div>
  );
}

function Metric({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <Card className="px-4 py-3">
      <p className="text-xs font-medium text-stone-500" title={hint}>
        {label}
        {hint && " ⓘ"}
      </p>
      <p className="mt-0.5 text-2xl font-semibold tabular-nums text-stone-900">{value}</p>
    </Card>
  );
}

function ThemeCard({ theme, points, total }: { theme: Theme; points: PainPoint[]; total: number }) {
  const [open, setOpen] = useState(false);
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold text-stone-400">{theme.id}</p>
          <h3 className="font-semibold text-stone-900">{theme.label}</h3>
          {theme.description && theme.description !== theme.label && (
            <p className="mt-0.5 text-sm text-stone-600">{theme.description}</p>
          )}
        </div>
        <div className="text-right">
          <p className="text-lg font-semibold tabular-nums text-stone-900">
            {theme.frequency}
            <span className="text-sm font-normal text-stone-500">/{total}</span>
          </p>
          <p className="text-[11px] text-stone-500">interviewees</p>
        </div>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-stone-100" aria-hidden>
        <div className="h-full bg-brand-600" style={{ width: `${theme.share * 100}%` }} />
      </div>
      <div className="mt-3 flex flex-wrap gap-1.5">
        <Pill tone={theme.top_intensity === "high" ? "rose" : "stone"}>{theme.top_intensity} intensity</Pill>
        {theme.paraphrase_only && <Pill tone="amber">notes only</Pill>}
        <Pill>{points.length} quotes</Pill>
      </div>
      <div className="mt-3 space-y-2">
        {(open ? points : points.slice(0, 1)).map((p) => (
          <QuoteCard key={p.id} evidence={p.evidence} />
        ))}
      </div>
      {points.length > 1 && (
        <button type="button" onClick={() => setOpen(!open)} className="mt-2 text-xs font-medium text-brand-700 hover:underline">
          {open ? "Show fewer" : `Show all ${points.length} quotes`}
        </button>
      )}
    </Card>
  );
}
