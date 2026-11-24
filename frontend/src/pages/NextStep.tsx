import { useEffect, useState } from "react";
import { api, ApiError, reportUrl } from "../api/client";
import type { FinalDecision, InterviewScript, Study } from "../api/types";
import { ScriptEditor, ScriptView } from "../components/ScriptEditor";
import { Banner, Button, Card, Pill, SectionTitle, Spinner, VerdictBadge } from "../components/ui";
import { FAILURE_HELP } from "../lib/labels";

type Props = { study: Study; refresh: () => Promise<Study | null> };

/** Step 4: approved decisions, the next interview script, and export. */
export function NextStep({ study, refresh }: Props) {
  const [decisions, setDecisions] = useState<FinalDecision[] | null>(null);
  const [script, setScript] = useState<InterviewScript | null | undefined>(undefined);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    api.decisions(study.id).then(setDecisions).catch((e: ApiError) => setError(e));
    api
      .script(study.id)
      .then(setScript)
      .catch((e: ApiError) => (e.code === "no_script" ? setScript(null) : setError(e)));
  }, [study.id, study.approved_at]);

  async function generate() {
    if (script?.edited_at && !window.confirm("Generating again replaces your edited script. Continue?")) return;
    setBusy(true);
    setError(null);
    try {
      setScript(await api.generateScript(study.id));
      setEditing(false);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "error", String(e)));
    } finally {
      setBusy(false);
      void refresh(); // token counter
    }
  }

  async function save(edits: Parameters<typeof api.saveScript>[1]): Promise<boolean> {
    setError(null);
    try {
      setScript(await api.saveScript(study.id, edits));
      setEditing(false);
      return true;
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "error", String(e)));
      return false;
    }
  }

  const help = error ? FAILURE_HELP[error.code] : undefined;
  const flagged = script?.questions.filter((q) => q.lint.length).length ?? 0;

  return (
    <div className="space-y-8">
      {error && (
        <Banner tone="rose" title={help?.title ?? "Something went wrong"}>
          <p>{error.message}</p>
          {help && <p>{help.action}</p>}
        </Banner>
      )}

      <section>
        <SectionTitle title="Your approved decisions" subtitle="These, not the AI suggestions, decide what the next interview asks." />
        {decisions ? (
          <div className="grid gap-2 md:grid-cols-2">
            {decisions.map((d) => (
              <Card key={d.hypothesis_id} className="flex items-start justify-between gap-3 p-3">
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-stone-400">{d.hypothesis_id}</p>
                  <p className="text-sm font-medium text-stone-900">{d.text}</p>
                  {d.reasoning && <p className="mt-0.5 text-xs text-stone-600">“{d.reasoning}”</p>}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  {d.final_verdict ? <VerdictBadge verdict={d.final_verdict} size="sm" /> : <Pill tone="rose">Re-test</Pill>}
                  {d.final_verdict !== d.ai_verdict && <span className="text-[11px] text-stone-500">AI: {d.ai_verdict}</span>}
                </div>
              </Card>
            ))}
          </div>
        ) : (
          !error && <Spinner />
        )}
      </section>

      <section>
        <SectionTitle
          title="Next interview script"
          subtitle="Non-leading questions aimed at what is still uncertain. Each comes with a bias check, and the wording is checked again by rules."
          right={
            script && !editing ? (
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => setEditing(true)}>
                  Edit
                </Button>
                <Button variant="secondary" disabled={busy} onClick={generate}>
                  {busy && <Spinner />} Regenerate
                </Button>
              </div>
            ) : null
          }
        />

        {script === undefined ? (
          <Spinner />
        ) : script === null ? (
          <Card className="p-6 text-center">
            <p className="text-sm text-stone-700">
              The script targets hypotheses you marked UNTESTED, MIXED or re-test, and digs into your strongest pain
              themes. Settled hypotheses are not asked again.
            </p>
            <Button className="mt-4" disabled={busy} onClick={generate}>
              {busy && <Spinner />} {busy ? "Drafting questions…" : "Draft the next interview script"}
            </Button>
            {busy && <p className="mt-2 text-xs text-stone-500">One model call; on a CPU this can take a minute.</p>}
          </Card>
        ) : (
          <div className="space-y-4">
            {script.warnings.map((w) => (
              <Banner key={w}>{w}</Banner>
            ))}
            {script.targets.length > 0 && (
              <details className="rounded-lg border border-stone-200 bg-white p-4 text-sm">
                <summary className="cursor-pointer font-medium text-stone-800">
                  Why these questions ({script.targets.length} targets)
                </summary>
                <ul className="mt-3 space-y-2">
                  {script.targets.map((t) => (
                    <li key={t.id}>
                      <Pill tone="brand">{t.id}</Pill> <span className="font-medium text-stone-900">{t.text}</span>
                      <p className="text-xs text-stone-600">{t.reason}</p>
                    </li>
                  ))}
                </ul>
              </details>
            )}
            {editing ? (
              <ScriptEditor script={script} onSave={save} onCancel={() => setEditing(false)} />
            ) : (
              <ScriptView script={script} />
            )}
            <p className="text-xs text-stone-500">
              {script.questions.length} questions · {flagged} with wording problems · drafted{" "}
              {new Date(script.generated_at).toLocaleString()}
              {script.model && ` with ${script.model} (${script.prompt_id})`}
              {script.edited_at && ` · edited ${new Date(script.edited_at).toLocaleString()}`}
            </p>
          </div>
        )}
      </section>

      <Card className="flex flex-wrap items-center justify-between gap-4 p-5">
        <div>
          <h2 className="font-semibold text-stone-900">Export the report</h2>
          <p className="text-sm text-stone-600">
            Decisions with every quote and its source, pain themes, the script, the decision log and AI usage.
          </p>
        </div>
        <div className="flex gap-2">
          <a href={reportUrl(study.id, "md")} download className={exportCls}>
            Markdown
          </a>
          <a href={reportUrl(study.id, "pdf")} download className={exportCls}>
            PDF
          </a>
        </div>
      </Card>
    </div>
  );
}

const exportCls =
  "inline-flex items-center rounded-lg bg-brand-800 px-3.5 py-2 text-sm font-medium text-white hover:bg-brand-900";
