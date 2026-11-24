import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Study } from "../api/types";
import { Banner, Button, Card, Pill, SectionTitle, Spinner, cx } from "../components/ui";
import { FAILURE_HELP, PROGRESS_STEPS } from "../lib/labels";

const MAX_HYPOTHESES = 10;
const ACCEPT = ".txt,.md,.markdown,.pdf,.docx";

type Props = {
  study: Study;
  setStudy: (s: Study) => void;
  refresh: () => Promise<Study | null>;
  goStep: (n: number) => void;
};

export function InputsStep({ study, setStudy, refresh, goStep }: Props) {
  const locked = study.status === "approved";
  const busy = study.status === "analyzing";
  const hasAnalysis = study.result !== null;
  const [error, setError] = useState<string | null>(null);
  const [hypothesesDirty, setHypothesesDirty] = useState(false);

  /** Changing inputs after an analysis throws the review away: ask first. */
  function confirmReset(): boolean {
    if (!hasAnalysis) return true;
    return window.confirm(
      "Changing interviews or hypotheses clears the current analysis and your review decisions (the decision log keeps a record). Continue?",
    );
  }

  return (
    <div className="space-y-6">
      {study.status === "analyzing" && <AnalysisProgress study={study} />}
      {study.status === "failed" && <FailureCard study={study} onRetry={() => startAnalysis()} />}
      {locked && (
        <Banner tone="brand" title="This study is approved and locked">
          Reopen the review on step 3 to change interviews or hypotheses.
        </Banner>
      )}
      {error && <Banner tone="rose" title="Could not do that">{error}</Banner>}

      <div className="grid gap-6 lg:grid-cols-5">
        <InterviewsCard
          study={study}
          disabled={locked || busy}
          confirmReset={confirmReset}
          onChanged={refresh}
          onError={setError}
        />
        <HypothesesCard
          key={study.hypotheses.map((h) => h.text).join("|")}
          study={study}
          disabled={locked || busy}
          confirmReset={confirmReset}
          onSaved={setStudy}
          onError={setError}
          onDirty={setHypothesesDirty}
        />
      </div>

      {study.corpus_warnings.length > 0 && (
        <Banner title="Before you analyse">
          {study.corpus_warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </Banner>
      )}

      <div className="flex flex-wrap items-center justify-end gap-3">
        {hypothesesDirty && <span className="text-sm text-amber-800">Save your hypotheses first.</span>}
        {hasAnalysis && (
          <Button variant="secondary" onClick={() => goStep(2)}>
            View evidence →
          </Button>
        )}
        <Button
          onClick={() => void startAnalysis()}
          disabled={
            locked ||
            busy ||
            hypothesesDirty ||
            study.interviews.length === 0 ||
            study.hypotheses.length === 0
          }
        >
          {busy && <Spinner />}
          {hasAnalysis ? "Re-run analysis" : "Run analysis"}
        </Button>
      </div>
    </div>
  );

  async function startAnalysis() {
    if (study.status === "awaiting_review" && Object.keys(study.reviews).length > 0) {
      if (!window.confirm("Re-running the analysis clears your review decisions. Continue?")) return;
    }
    setError(null);
    try {
      await api.analyze(study.id);
      const s = await refresh();
      if (s?.status === "awaiting_review") goStep(2);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }
}

function AnalysisProgress({ study }: { study: Study }) {
  const current = PROGRESS_STEPS.findIndex((s) => s.key === study.progress);
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-semibold text-stone-900">
          <Spinner /> Analysing {study.interviews.length} interviews
        </h2>
        <span className="text-xs tabular-nums text-stone-500">{study.cost_label}</span>
      </div>
      <ol className="mt-4 space-y-2">
        {PROGRESS_STEPS.map((s, i) => (
          <li
            key={s.key}
            className={cx(
              "flex items-center gap-2 text-sm",
              i < current ? "text-stone-500" : i === current ? "font-medium text-stone-900" : "text-stone-400",
            )}
          >
            <span className="w-4 text-center">{i < current ? "✓" : i === current ? "●" : "○"}</span>
            {s.label}
          </li>
        ))}
      </ol>
      <p className="mt-4 text-xs text-stone-500">
        On a laptop CPU a local 7B model can take several minutes. You can leave this page open; it
        updates by itself.
      </p>
    </Card>
  );
}

function FailureCard({ study, onRetry }: { study: Study; onRetry: () => void }) {
  const help = FAILURE_HELP[study.error_kind ?? "internal"] ?? FAILURE_HELP.internal!;
  return (
    <Banner tone="rose" title={help.title}>
      <p>{help.action}</p>
      {study.error && <p className="font-mono text-xs opacity-80">{study.error}</p>}
      <div className="pt-2">
        <Button variant="danger" onClick={onRetry}>
          Try again
        </Button>
      </div>
    </Banner>
  );
}

function InterviewsCard({
  study,
  disabled,
  confirmReset,
  onChanged,
  onError,
}: {
  study: Study;
  disabled: boolean;
  confirmReset: () => boolean;
  onChanged: () => Promise<unknown>;
  onError: (msg: string | null) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [fileErrors, setFileErrors] = useState<{ filename: string; error: string }[]>([]);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteTitle, setPasteTitle] = useState("");
  const [pasteText, setPasteText] = useState("");

  async function upload(files: File[]) {
    if (!files.length || !confirmReset()) return;
    setUploading(true);
    onError(null);
    try {
      const r = await api.upload(study.id, files);
      setFileErrors(r.errors);
      await onChanged();
    } catch (e) {
      onError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  async function paste() {
    if (!pasteText.trim() || !confirmReset()) return;
    onError(null);
    try {
      await api.paste(study.id, pasteText, pasteTitle);
      setPasteText("");
      setPasteTitle("");
      setPasteOpen(false);
      await onChanged();
    } catch (e) {
      onError(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function remove(id: string) {
    if (!confirmReset()) return;
    try {
      await api.removeInterview(study.id, id);
      await onChanged();
    } catch (e) {
      onError(e instanceof ApiError ? e.message : String(e));
    }
  }

  return (
    <Card className="p-5 lg:col-span-3">
      <SectionTitle
        title={`Interviews (${study.interviews.length})`}
        subtitle="Transcripts or notes: .txt, .md, .pdf or .docx. Label speakers like “Interviewer:” and “Maya:”."
      />
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!disabled) void upload(Array.from(e.dataTransfer.files));
        }}
        className={cx(
          "flex flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-6 text-center transition",
          dragging ? "border-brand-600 bg-brand-50" : "border-stone-300 bg-stone-50",
          disabled && "opacity-50",
        )}
      >
        <p className="text-sm text-stone-700">
          Drop files here, or{" "}
          <button
            type="button"
            disabled={disabled}
            onClick={() => input.current?.click()}
            className="font-medium text-brand-700 underline-offset-2 hover:underline disabled:no-underline"
          >
            choose files
          </button>{" "}
          ·{" "}
          <button
            type="button"
            disabled={disabled}
            onClick={() => setPasteOpen((o) => !o)}
            className="font-medium text-brand-700 underline-offset-2 hover:underline disabled:no-underline"
          >
            paste text
          </button>
        </p>
        <p className="mt-1 text-xs text-stone-500">
          Remove names and personal details you do not need before uploading.
        </p>
        <input
          ref={input}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            void upload(Array.from(e.target.files ?? []));
            e.target.value = "";
          }}
        />
        {uploading && (
          <p className="mt-2 flex items-center gap-2 text-sm text-stone-600">
            <Spinner /> Parsing…
          </p>
        )}
      </div>

      {pasteOpen && (
        <div className="mt-3 space-y-2">
          <input
            value={pasteTitle}
            onChange={(e) => setPasteTitle(e.target.value)}
            placeholder="Interview name (optional)"
            aria-label="Interview name"
            className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-brand-600 focus:outline-none"
          />
          <textarea
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            rows={6}
            aria-label="Interview text"
            placeholder={"Interviewer: How do you get paid?\nMaya: Usually late…"}
            className="w-full rounded-lg border border-stone-300 px-3 py-2 font-mono text-sm focus:border-brand-600 focus:outline-none"
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setPasteOpen(false)}>Cancel</Button>
            <Button variant="secondary" onClick={() => void paste()} disabled={!pasteText.trim()}>
              Add interview
            </Button>
          </div>
        </div>
      )}

      {fileErrors.length > 0 && (
        <div className="mt-3">
          <Banner tone="rose" title="Some files were not added">
            {fileErrors.map((f) => (
              <p key={f.filename}>
                <span className="font-medium">{f.filename}</span>: {f.error}
              </p>
            ))}
          </Banner>
        </div>
      )}

      <ul className="mt-4 divide-y divide-stone-100">
        {study.interviews.map((t) => (
          <li key={t.id} className="flex items-start justify-between gap-3 py-2.5">
            <div className="min-w-0">
              <p className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-medium text-stone-900">{t.id}</span>
                <span className="truncate text-stone-600">{t.title}</span>
                {t.format === "notes" && <Pill tone="amber">notes, paraphrase</Pill>}
              </p>
              <p className="text-xs text-stone-500">
                {t.customer_segments} customer segments of {t.segments}
                {t.source_filename && ` · ${t.source_filename}`}
              </p>
              {t.warnings.map((w) => (
                <p key={w} className="mt-0.5 text-xs text-amber-800">{w}</p>
              ))}
            </div>
            <Button variant="ghost" disabled={disabled} onClick={() => void remove(t.id)} aria-label={`Remove ${t.id}`}>
              Remove
            </Button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function HypothesesCard({
  study,
  disabled,
  confirmReset,
  onSaved,
  onError,
  onDirty,
}: {
  study: Study;
  disabled: boolean;
  confirmReset: () => boolean;
  onSaved: (s: Study) => void;
  onError: (msg: string | null) => void;
  onDirty: (dirty: boolean) => void;
}) {
  const initial = study.hypotheses.map((h) => h.text);
  const [items, setItems] = useState<string[]>(initial.length ? initial : [""]);
  const [saving, setSaving] = useState(false);
  const dirty = JSON.stringify(items.filter((t) => t.trim())) !== JSON.stringify(initial);

  useEffect(() => onDirty(dirty), [dirty, onDirty]);

  async function save() {
    if (!confirmReset()) return;
    setSaving(true);
    try {
      onSaved(await api.setHypotheses(study.id, items.filter((t) => t.trim())));
    } catch (e) {
      onError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card className="p-5 lg:col-span-2">
      <SectionTitle
        title="Hypotheses"
        subtitle="One belief per line, stated so an interview could prove it wrong."
      />
      <ol className="space-y-2">
        {items.map((text, i) => (
          <li key={i} className="flex items-start gap-2">
            <span className="mt-2 w-6 text-xs font-semibold text-stone-400">H{i + 1}</span>
            <textarea
              value={text}
              disabled={disabled}
              rows={2}
              maxLength={500}
              aria-label={`Hypothesis ${i + 1}`}
              placeholder="e.g. Freelancers struggle to chase late invoices."
              onChange={(e) => setItems(items.map((t, j) => (j === i ? e.target.value : t)))}
              className="min-w-0 flex-1 resize-none rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-brand-600 focus:outline-none disabled:bg-stone-50"
            />
            <button
              type="button"
              disabled={disabled || items.length === 1}
              onClick={() => setItems(items.filter((_, j) => j !== i))}
              className="mt-2 text-stone-400 hover:text-rose-600 disabled:opacity-30"
              aria-label={`Remove hypothesis ${i + 1}`}
            >
              ✕
            </button>
          </li>
        ))}
      </ol>
      <div className="mt-3 flex items-center justify-between">
        <Button
          variant="ghost"
          disabled={disabled || items.length >= MAX_HYPOTHESES}
          onClick={() => setItems([...items, ""])}
        >
          + Add hypothesis
        </Button>
        <Button variant="secondary" disabled={disabled || !dirty || saving} onClick={() => void save()}>
          {saving && <Spinner />} {dirty ? "Save hypotheses" : "Saved"}
        </Button>
      </div>
    </Card>
  );
}
