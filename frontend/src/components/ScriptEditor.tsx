import { useState } from "react";
import type { InterviewScript, QuestionEdit, ScriptQuestion, ScriptSection } from "../api/types";
import { Button, Pill, Spinner, cx } from "./ui";

export const SECTION_TITLE: Record<ScriptSection, string> = {
  warmup: "Warm-up",
  pain_followup: "Pain follow-ups",
  hypothesis: "Hypotheses to test",
  custom: "Your own questions",
  wrapup: "Wrap-up",
};

const SECTION_ORDER: ScriptSection[] = ["warmup", "pain_followup", "hypothesis", "custom", "wrapup"];

/** Read-only view of the script, grouped by section. */
export function ScriptView({ script }: { script: InterviewScript }) {
  return (
    <div className="space-y-6">
      {SECTION_ORDER.map((section) => {
        const qs = script.questions.filter((q) => q.section === section);
        if (!qs.length) return null;
        return (
          <section key={section}>
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-stone-500">{SECTION_TITLE[section]}</h3>
            <ol className="space-y-3">
              {qs.map((q) => (
                <QuestionCard key={q.id} q={q} />
              ))}
            </ol>
          </section>
        );
      })}
    </div>
  );
}

function QuestionCard({ q }: { q: ScriptQuestion }) {
  return (
    <li className={cx("rounded-lg border bg-white p-4", q.lint.length ? "border-amber-300" : "border-stone-200")}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-semibold text-stone-400">{q.id}</span>
        {q.target && <Pill tone="brand">{q.target}</Pill>}
        {q.edited && <Pill>edited by you</Pill>}
      </div>
      {q.needs_edit ? (
        <p className="mt-1 text-sm italic text-stone-500">To be written: {q.purpose}</p>
      ) : (
        <p className="mt-1 text-[15px] font-medium leading-snug text-stone-900">{q.question}</p>
      )}
      {q.follow_ups.length > 0 && (
        <ul className="mt-2 space-y-0.5 text-sm text-stone-700">
          {q.follow_ups.map((f) => (
            <li key={f}>↳ {f}</li>
          ))}
        </ul>
      )}
      <dl className="mt-2 grid gap-x-3 gap-y-1 text-xs text-stone-600 sm:grid-cols-[auto_1fr]">
        {q.purpose && !q.needs_edit && (
          <>
            <dt className="font-medium text-stone-700">Purpose</dt>
            <dd>{q.purpose}</dd>
          </>
        )}
        {q.bias_check && (
          <>
            <dt className="font-medium text-stone-700">Bias check</dt>
            <dd>{q.bias_check}</dd>
          </>
        )}
      </dl>
      {q.lint.length > 0 && (
        <ul className="mt-2 space-y-1 rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-950" aria-label="Wording problems">
          {q.lint.map((l) => (
            <li key={l}>⚠ {l}</li>
          ))}
        </ul>
      )}
    </li>
  );
}

type Draft = { key: string; id: string | null; question: string; followUps: string; purpose: string; section: ScriptSection; target: string | null };

let counter = 0;
const toDraft = (q: ScriptQuestion): Draft => ({
  key: q.id,
  id: q.id,
  question: q.question,
  followUps: q.follow_ups.join("\n"),
  purpose: q.purpose,
  section: q.section,
  target: q.target,
});

/** Edit, reorder, add and remove questions. The server re-checks the wording on save. */
export function ScriptEditor({
  script,
  onSave,
  onCancel,
}: {
  script: InterviewScript;
  onSave: (edits: QuestionEdit[]) => Promise<boolean>;
  onCancel: () => void;
}) {
  const [drafts, setDrafts] = useState<Draft[]>(() => script.questions.map(toDraft));
  const [saving, setSaving] = useState(false);
  const empty = drafts.some((d) => !d.question.trim());

  function update(i: number, patch: Partial<Draft>) {
    setDrafts(drafts.map((d, j) => (j === i ? { ...d, ...patch } : d)));
  }
  function move(i: number, by: number) {
    const j = i + by;
    if (j < 0 || j >= drafts.length) return;
    const next = [...drafts];
    [next[i], next[j]] = [next[j]!, next[i]!];
    setDrafts(next);
  }
  function add() {
    counter += 1;
    setDrafts([...drafts.slice(0, -2), { key: `new-${counter}`, id: null, question: "", followUps: "", purpose: "", section: "custom", target: null }, ...drafts.slice(-2)]);
  }
  async function save() {
    setSaving(true);
    try {
      await onSave(
        drafts.map((d) => ({
          id: d.id,
          question: d.question,
          follow_ups: d.followUps.split("\n").map((s) => s.trim()).filter(Boolean),
          purpose: d.purpose,
        })),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3">
      {drafts.map((d, i) => (
        <div key={d.key} className="rounded-lg border border-stone-200 bg-white p-3">
          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
            <span className="font-semibold text-stone-400">{d.id ?? "new"}</span>
            <Pill>{SECTION_TITLE[d.section]}</Pill>
            {d.target && <Pill tone="brand">{d.target}</Pill>}
            <span className="ml-auto flex gap-1">
              <Button variant="ghost" className="px-2 py-1" aria-label={`Move ${d.id ?? "question"} up`} disabled={i === 0} onClick={() => move(i, -1)}>
                ↑
              </Button>
              <Button variant="ghost" className="px-2 py-1" aria-label={`Move ${d.id ?? "question"} down`} disabled={i === drafts.length - 1} onClick={() => move(i, 1)}>
                ↓
              </Button>
              <Button variant="ghost" className="px-2 py-1 text-rose-700" aria-label={`Remove ${d.id ?? "question"}`} onClick={() => setDrafts(drafts.filter((_, j) => j !== i))}>
                Remove
              </Button>
            </span>
          </div>
          <label className="block text-xs font-medium text-stone-600">
            Question
            <textarea
              value={d.question}
              onChange={(e) => update(i, { question: e.target.value })}
              rows={2}
              maxLength={400}
              placeholder={d.purpose ? `Write a question to: ${d.purpose}` : "Ask about a specific past event"}
              className="mt-1 block w-full rounded-md border border-stone-300 px-2.5 py-1.5 text-sm text-stone-900"
            />
          </label>
          <label className="mt-2 block text-xs font-medium text-stone-600">
            Follow-ups (one per line)
            <textarea
              value={d.followUps}
              onChange={(e) => update(i, { followUps: e.target.value })}
              rows={1}
              className="mt-1 block w-full rounded-md border border-stone-300 px-2.5 py-1.5 text-sm text-stone-900"
            />
          </label>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={add}>
          + Add a question
        </Button>
        <span className="flex-1" />
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button disabled={saving || empty || drafts.length === 0} onClick={save}>
          {saving && <Spinner />} Save script
        </Button>
      </div>
      {empty && <p className="text-right text-xs text-stone-500">Fill in or remove empty questions before saving.</p>}
    </div>
  );
}
