import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { Decision, HypothesisVerdict, Review, Study, Verdict } from "../api/types";
import { DecisionLog } from "../components/DecisionLog";
import { QuoteCard } from "../components/QuoteCard";
import { Banner, Button, Card, Pill, Spinner, VerdictBadge, cx } from "../components/ui";
import { ALL_VERDICTS, CONFIDENCE_LABEL } from "../lib/labels";

type Props = { study: Study; setStudy: (s: Study) => void; goStep: (n: number) => void };

/** Step 3: the human checkpoint. Nothing downstream runs until this is approved. */
export function ReviewStep({ study, setStudy, goStep }: Props) {
  const result = study.result!;
  const cp = study.checkpoint;
  const approved = study.status === "approved";
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reopenReason, setReopenReason] = useState("");

  /** Run a write, store the returned study; resolves false (and shows why) on failure. */
  async function act(fn: () => Promise<Study>, after?: () => void): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      setStudy(await fn());
      after?.();
      return true;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  const blocked = !cp.can_approve || (cp.needs_small_sample_ack && !ack);
  const blockReason = cp.missing.length
    ? `Review ${cp.missing.length} more verdict${cp.missing.length > 1 ? "s" : ""} (${cp.missing.join(", ")}) to continue.`
    : cp.needs_small_sample_ack && !ack
      ? "Confirm you understand the small-sample limitation to continue."
      : null;

  return (
    <div className="space-y-6">
      <Banner tone="brand" title="Human checkpoint">
        <p>
          Each verdict below is an AI suggestion. Approve it, change it, or reject it as untrustworthy,
          and remove any quote you think was misread. Your decisions, not the AI's, drive the next
          interview script. Nothing moves on until you approve.
        </p>
      </Banner>

      <div className="flex items-center gap-3">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-stone-200" aria-hidden>
          <div className="h-full bg-brand-600 transition-all" style={{ width: `${(cp.reviewed / (cp.total || 1)) * 100}%` }} />
        </div>
        <p className="text-sm font-medium tabular-nums text-stone-700" aria-live="polite">
          {cp.reviewed} of {cp.total} reviewed
        </p>
      </div>

      {error && <Banner tone="rose" title="Could not save">{error}</Banner>}

      <div className="space-y-4">
        {result.verdicts.map((v) => (
          <ReviewCard
            key={v.hypothesis.id}
            v={v}
            review={study.reviews[v.hypothesis.id]}
            locked={approved}
            onSave={(input) => act(() => api.review(study.id, v.hypothesis.id, input))}
          />
        ))}
      </div>

      <Card className="p-5">
        {approved ? (
          <div className="space-y-3">
            <p className="text-sm text-stone-700">
              Approved {study.approved_at && new Date(study.approved_at).toLocaleString()}. Decisions are locked.
            </p>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => goStep(4)}>Go to next interview →</Button>
            </div>
            <details className="text-sm">
              <summary className="cursor-pointer text-stone-600">Reopen the review</summary>
              <div className="mt-2 flex flex-wrap gap-2">
                <input
                  value={reopenReason}
                  onChange={(e) => setReopenReason(e.target.value)}
                  placeholder="Why are you reopening it?"
                  aria-label="Reason for reopening"
                  className="min-w-0 flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm"
                />
                <Button variant="secondary" disabled={busy} onClick={() => act(() => api.reopen(study.id, reopenReason))}>
                  Reopen
                </Button>
              </div>
            </details>
          </div>
        ) : (
          <div className="space-y-3">
            {cp.needs_small_sample_ack && (
              <label className="flex items-start gap-2 text-sm text-stone-800">
                <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-0.5 size-4 accent-brand-700" />
                <span>
                  I understand these verdicts come from only {result.interview_count} interview
                  {result.interview_count === 1 ? "" : "s"} and are provisional.
                </span>
              </label>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <Button
                disabled={blocked || busy}
                onClick={() => act(() => api.approve(study.id, ack), () => goStep(4))}
              >
                {busy && <Spinner />} Approve and continue
              </Button>
              {blockReason && <p className="text-sm text-stone-600">{blockReason}</p>}
            </div>
          </div>
        )}
      </Card>

      <DecisionLog studyId={study.id} version={study.updated_at} />
    </div>
  );
}

const DECISIONS: { value: Decision; label: string; help: string }[] = [
  { value: "approve", label: "Accept", help: "The AI suggestion matches my reading." },
  { value: "change", label: "Change", help: "The evidence supports a different verdict." },
  { value: "reject", label: "Reject", help: "I don't trust this evidence; re-test it." },
];

function ReviewCard({
  v,
  review,
  locked,
  onSave,
}: {
  v: HypothesisVerdict;
  review?: Review;
  locked: boolean;
  onSave: (input: { decision: Decision; verdict?: Verdict | null; reasoning: string; removed_evidence: string[]; note: string }) => Promise<boolean>;
}) {
  const [editing, setEditing] = useState(!review);
  const [decision, setDecision] = useState<Decision>(review?.decision ?? "approve");
  // No preselected alternative: the founder must pick one deliberately.
  const [verdict, setVerdict] = useState<Verdict | "">(
    review?.decision === "change" && review.final_verdict ? review.final_verdict : "",
  );
  const [reasoning, setReasoning] = useState(review?.reasoning ?? "");
  const [note, setNote] = useState(review?.note ?? "");
  const [removed, setRemoved] = useState<Set<string>>(new Set(review?.removed_evidence ?? []));
  const [saving, setSaving] = useState(false);

  const needsReason = decision !== "approve";
  const missingVerdict = decision === "change" && !verdict;
  const shortReason = needsReason && reasoning.trim().length < 5;
  const invalid = missingVerdict || shortReason;
  const quotes = [
    ...v.supporting.map((e) => ({ e, tone: "for" as const })),
    ...v.contradicting.map((e) => ({ e, tone: "against" as const })),
  ];

  function toggle(key: string) {
    const next = new Set(removed);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setRemoved(next);
  }

  async function save() {
    setSaving(true);
    try {
      const ok = await onSave({
        decision,
        verdict: decision === "change" && verdict ? verdict : null,
        reasoning,
        removed_evidence: [...removed],
        note,
      });
      if (ok) setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  const id = `rv-${v.hypothesis.id}`;
  return (
    <Card className={cx("p-5", review && !editing && "border-brand-200")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-stone-400">{v.hypothesis.id}</p>
          <h3 className="font-semibold text-stone-900">{v.hypothesis.text}</h3>
          <p className="mt-1 text-xs text-stone-500">
            {v.counts.supports} support · {v.counts.mixed} mixed · {v.counts.contradicts} contradict ·{" "}
            {v.counts.not_discussed} not discussed · {CONFIDENCE_LABEL[v.confidence]}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-stone-500">
            {review ? "Your decision" : "AI suggestion"}
          </span>
          {review ? (
            review.final_verdict ? <VerdictBadge verdict={review.final_verdict} /> : <Pill tone="rose">Re-test</Pill>
          ) : (
            <VerdictBadge verdict={v.verdict} />
          )}
          {review && review.final_verdict !== v.verdict && (
            <span className="text-xs text-stone-500">AI suggested {v.verdict}</span>
          )}
        </div>
      </div>

      {review && !editing ? (
        <div className="mt-3 space-y-2 text-sm">
          <p className="text-stone-700">
            <span className="font-medium capitalize">{review.decision === "approve" ? "Accepted" : review.decision === "change" ? "Changed" : "Rejected"}</span>
            {review.reasoning && <>: “{review.reasoning}”</>}
          </p>
          {review.removed_evidence.length > 0 && (
            <p className="text-stone-600">{review.removed_evidence.length} quote(s) removed as evidence.</p>
          )}
          {review.recomputed_ai_verdict !== review.ai_verdict && (
            <Banner title="The quotes you removed change the arithmetic">
              Without them, the rules would suggest <strong>{review.recomputed_ai_verdict}</strong> instead of{" "}
              {review.ai_verdict}. Consider whether your decision still holds.
            </Banner>
          )}
          {review.note && <p className="text-stone-600">Note: {review.note}</p>}
          <p className="text-xs text-stone-500">Saved {new Date(review.reviewed_at).toLocaleString()}</p>
          {!locked && (
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Edit decision
            </Button>
          )}
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          <fieldset>
            <legend className="sr-only">Decision for {v.hypothesis.id}</legend>
            <div className="grid gap-2 sm:grid-cols-3">
              {DECISIONS.map((d) => (
                <label
                  key={d.value}
                  className={cx(
                    "cursor-pointer rounded-lg border px-3 py-2 text-sm",
                    decision === d.value ? "border-brand-600 bg-brand-50 ring-1 ring-brand-600" : "border-stone-200 hover:bg-stone-50",
                  )}
                >
                  <input
                    type="radio"
                    name={id}
                    value={d.value}
                    checked={decision === d.value}
                    onChange={() => setDecision(d.value)}
                    className="sr-only"
                  />
                  <span className="font-medium text-stone-900">
                    {d.label}
                    {d.value === "approve" && <> <VerdictBadge verdict={v.verdict} size="sm" /></>}
                  </span>
                  <span className="block text-xs text-stone-600">{d.help}</span>
                </label>
              ))}
            </div>
          </fieldset>

          {decision === "change" && (
            <label className="block text-sm">
              <span className="font-medium text-stone-800">Your verdict</span>
              <select
                value={verdict}
                onChange={(e) => setVerdict(e.target.value as Verdict)}
                className="mt-1 block rounded-lg border border-stone-300 px-3 py-2 text-sm"
              >
                <option value="" disabled>
                  Choose a verdict…
                </option>
                {ALL_VERDICTS.filter((x) => x !== v.verdict).map((x) => (
                  <option key={x} value={x}>
                    {x}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className="block text-sm">
            <span className="font-medium text-stone-800">
              Reasoning {needsReason ? <span className="text-rose-700">(required)</span> : <span className="text-stone-500">(optional)</span>}
            </span>
            <textarea
              value={reasoning}
              onChange={(e) => setReasoning(e.target.value)}
              rows={2}
              maxLength={2000}
              placeholder={needsReason ? "Why? This goes in the decision log." : "Anything worth recording?"}
              className="mt-1 block w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
            />
          </label>

          {quotes.length > 0 && (
            <details className="text-sm">
              <summary className="cursor-pointer font-medium text-stone-800">
                Remove misread quotes ({removed.size} of {quotes.length} removed)
              </summary>
              <ul className="mt-2 space-y-2">
                {quotes.map(({ e, tone }) => (
                  <li key={e.key} className="flex items-start gap-2">
                    <input
                      type="checkbox"
                      aria-label={`Remove quote ${e.key}`}
                      checked={removed.has(e.key)}
                      onChange={() => toggle(e.key)}
                      className="mt-3 size-4 accent-rose-600"
                    />
                    <div className="min-w-0 flex-1">
                      <QuoteCard evidence={e} tone={tone} struck={removed.has(e.key)} />
                    </div>
                  </li>
                ))}
              </ul>
            </details>
          )}

          <label className="block text-sm">
            <span className="font-medium text-stone-800">Note</span> <span className="text-stone-500">(optional)</span>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={2000}
              className="mt-1 block w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
            />
          </label>

          <div className="flex items-center gap-2">
            <Button disabled={invalid || saving || locked} onClick={save}>
              {saving && <Spinner />} Save decision
            </Button>
            {review && (
              <Button variant="ghost" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            )}
            {invalid && (
              <span className="text-xs text-stone-500">
                {missingVerdict ? "Choose your verdict." : "Add a short reason (5+ characters)."}
              </span>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
