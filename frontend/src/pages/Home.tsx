import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { SampleSet, StudySummary } from "../api/types";
import { Banner, Button, Card, Pill, Spinner } from "../components/ui";

const STATUS_LABEL: Record<string, string> = {
  draft: "Draft",
  analyzing: "Analysing",
  awaiting_review: "Awaiting your review",
  approved: "Approved",
  failed: "Analysis failed",
};

export function Home({ onOpen }: { onOpen: (id: string) => void }) {
  const [samples, setSamples] = useState<SampleSet[]>([]);
  const [studies, setStudies] = useState<StudySummary[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [demo, setDemo] = useState(false);

  useEffect(() => {
    api.samples().then(setSamples).catch(() => {});
    api.health().then((h) => setDemo(h.llm.provider === "demo")).catch(() => {});
    api.studies().then(setStudies).catch((e: ApiError) => setError(e.message));
  }, []);

  async function run(key: string, fn: () => Promise<{ id: string }>) {
    setBusy(key);
    setError(null);
    try {
      onOpen((await fn()).id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function remove(s: StudySummary) {
    if (!window.confirm(`Delete “${s.name}” with its interviews, decisions and log? This cannot be undone.`)) return;
    try {
      await api.deleteStudy(s.id);
      setStudies((all) => all.filter((x) => x.id !== s.id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  return (
    <div className="space-y-10">
      <section className="max-w-3xl">
        <h1 className="text-3xl font-semibold tracking-tight text-stone-900 sm:text-4xl">
          Turn customer interviews into decisions you can defend.
        </h1>
        <p className="mt-3 text-base leading-relaxed text-stone-600">
          Upload interview transcripts and state your hypotheses. Groundwork finds pain points tied to
          verbatim, verified quotes, groups them into themes, and suggests a verdict for each
          hypothesis. <strong className="font-semibold text-stone-800">You review every verdict</strong>{" "}
          before it drafts your next interview script.
        </p>
        <p className="mt-2 text-sm text-stone-500">
          Runs on free, open-weight models. With Ollama, your interviews never leave your machine.
        </p>
      </section>

      {error && <Banner tone="rose" title="Something went wrong">{error}</Banner>}
      {demo && (
        <Banner tone="brand" title="Demo mode: no language model is running">
          <p>
            Answers are replayed from hand labels for the three sample sets, so you can try the whole flow in
            seconds. Quote verification, theme frequencies, verdict rules and your review are all real. Your own
            interviews will return no findings until you switch <code>LLM_PROVIDER</code> to <code>ollama</code>.
          </p>
        </Banner>
      )}

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-stone-500">
          Try it with sample data
        </h2>
        <div className="grid gap-4 md:grid-cols-3">
          {samples.map((s) => (
            <Card key={s.id} className="flex flex-col p-5">
              <h3 className="font-semibold text-stone-900">{s.name}</h3>
              <p className="mt-1 flex-1 text-sm text-stone-600">{s.description}</p>
              <div className="mt-4 flex items-center justify-between">
                <Pill tone={s.interview_count < 5 ? "amber" : "stone"}>{s.interview_count} interviews</Pill>
                <Button
                  variant="secondary"
                  disabled={busy !== null}
                  onClick={() => run(s.id, () => api.createFromSample(s.id))}
                >
                  {busy === s.id && <Spinner />} Open
                </Button>
              </div>
            </Card>
          ))}
        </div>
        <p className="mt-2 text-xs text-stone-500">All sample interviews are fictional.</p>
      </section>

      <section className="grid gap-6 md:grid-cols-2">
        <Card className="p-5">
          <h2 className="font-semibold text-stone-900">Start a new study</h2>
          <p className="mt-1 text-sm text-stone-600">Name it after the customer segment or question you are exploring.</p>
          <form
            className="mt-4 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void run("new", () => api.createStudy(name || "Untitled study"));
            }}
          >
            <label className="sr-only" htmlFor="study-name">Study name</label>
            <input
              id="study-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Freelancers and late payments"
              maxLength={200}
              className="min-w-0 flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-600/20"
            />
            <Button type="submit" disabled={busy !== null}>
              {busy === "new" && <Spinner />} Create
            </Button>
          </form>
        </Card>

        <Card className="p-5">
          <h2 className="font-semibold text-stone-900">Your studies</h2>
          {studies.length === 0 ? (
            <p className="mt-2 text-sm text-stone-500">No studies yet.</p>
          ) : (
            <ul className="mt-3 divide-y divide-stone-100">
              {studies.slice(0, 8).map((s) => (
                <li key={s.id} className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => onOpen(s.id)}
                    className="flex min-w-0 flex-1 items-center justify-between gap-3 py-2 text-left text-sm hover:text-brand-800"
                  >
                    <span className="truncate font-medium">{s.name}</span>
                    <span className="shrink-0 text-xs text-stone-500">
                      {s.interviews} interviews · {STATUS_LABEL[s.status] ?? s.status}
                    </span>
                  </button>
                  <button
                    type="button"
                    aria-label={`Delete ${s.name}`}
                    title="Delete this study and all its data"
                    disabled={s.status === "analyzing"}
                    onClick={() => void remove(s)}
                    className="rounded px-1.5 py-1 text-xs text-stone-400 hover:bg-rose-50 hover:text-rose-700 disabled:opacity-40"
                  >
                    Delete
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>
    </div>
  );
}
