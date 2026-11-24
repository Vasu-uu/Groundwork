import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../api/client";
import type { Evidence, Transcript } from "../api/types";
import { splitAt } from "../lib/highlight";
import { Button, Pill, Spinner } from "./ui";

type Open = (evidence: Evidence) => void;
const SourceContext = createContext<Open>(() => {});

/** Any quote card can call this to show its source in the side panel. */
export const useOpenSource = () => useContext(SourceContext);

export function SourceProvider({ studyId, children }: { studyId: string; children: ReactNode }) {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  return (
    <SourceContext.Provider value={setEvidence}>
      {children}
      {evidence && (
        <SourcePanel studyId={studyId} evidence={evidence} onClose={() => setEvidence(null)} />
      )}
    </SourceContext.Provider>
  );
}

/** Slide-over showing the original transcript with the cited quote highlighted. */
function SourcePanel({
  studyId,
  evidence,
  onClose,
}: {
  studyId: string;
  evidence: Evidence;
  onClose: () => void;
}) {
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mark = useRef<HTMLElement>(null);

  useEffect(() => {
    let live = true;
    setTranscript(null);
    api
      .transcript(studyId, evidence.interview_id)
      .then((t) => live && setTranscript(t))
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [studyId, evidence.interview_id]);

  useEffect(() => {
    mark.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [transcript, evidence.key]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const [before, hit, after] = transcript
    ? splitAt(transcript.text, evidence.start, evidence.end)
    : ["", "", ""];

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label="Source transcript">
      <button type="button" aria-label="Close source" className="flex-1 bg-stone-900/30" onClick={onClose} />
      <aside className="flex h-full w-full max-w-xl flex-col border-l border-stone-200 bg-white shadow-2xl">
        <header className="flex items-start justify-between gap-3 border-b border-stone-200 px-5 py-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-stone-500">Source</p>
            <h3 className="font-semibold text-stone-900">{transcript?.title ?? evidence.interview_id}</h3>
            <div className="mt-1 flex flex-wrap gap-1.5">
              <Pill>{evidence.interview_id}</Pill>
              <Pill>Segment {evidence.segment}</Pill>
              <Pill>{evidence.speaker}</Pill>
              {evidence.paraphrase && <Pill tone="amber">Founder notes: paraphrase</Pill>}
              <Pill tone="brand">
                {evidence.match === "exact" ? "Exact match" : `Fuzzy match ${Math.round(evidence.score * 100)}%`}
              </Pill>
            </div>
          </div>
          <Button variant="ghost" onClick={onClose} aria-label="Close">
            ✕
          </Button>
        </header>
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {error && <p className="text-sm text-rose-700">{error}</p>}
          {!transcript && !error && (
            <p className="flex items-center gap-2 text-sm text-stone-500">
              <Spinner /> Loading transcript…
            </p>
          )}
          {transcript && (
            <pre className="whitespace-pre-wrap font-serif text-[15px] leading-7 text-stone-700">
              {before}
              <mark ref={mark} className="source-hit">
                {hit}
              </mark>
              {after}
            </pre>
          )}
        </div>
        <footer className="border-t border-stone-200 px-5 py-3 text-xs text-stone-500">
          Highlighted text is the transcript's own wording, located by quote verification.
        </footer>
      </aside>
    </div>
  );
}
