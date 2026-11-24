import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { FinalDecision, Study } from "../api/types";
import { Banner, Card, Pill, SectionTitle, VerdictBadge } from "../components/ui";

/** Step 4: the approved decisions. Script generation and export land in Stage 7. */
export function NextStep({ study }: { study: Study }) {
  const [decisions, setDecisions] = useState<FinalDecision[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .decisions(study.id)
      .then(setDecisions)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [study.id, study.updated_at]);

  if (error) return <Banner tone="rose" title="Not available yet">{error}</Banner>;
  if (!decisions) return null;

  const retest = decisions.filter((d) => d.final_verdict === null || d.final_verdict === "UNTESTED" || d.final_verdict === "MIXED");
  return (
    <div className="space-y-6">
      <SectionTitle title="Your approved decisions" subtitle="These, not the AI suggestions, drive what you ask next." />
      <div className="space-y-3">
        {decisions.map((d) => (
          <Card key={d.hypothesis_id} className="flex flex-wrap items-start justify-between gap-3 p-4">
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-stone-400">{d.hypothesis_id}</p>
              <p className="font-medium text-stone-900">{d.text}</p>
              {d.reasoning && <p className="mt-1 text-sm text-stone-600">“{d.reasoning}”</p>}
              <p className="mt-1 text-xs text-stone-500">
                {d.supporting.length} supporting · {d.contradicting.length} contradicting quotes kept
              </p>
            </div>
            <div className="flex flex-col items-end gap-1">
              {d.final_verdict ? <VerdictBadge verdict={d.final_verdict} /> : <Pill tone="rose">Re-test</Pill>}
              {d.final_verdict !== d.ai_verdict && <span className="text-xs text-stone-500">AI suggested {d.ai_verdict}</span>}
            </div>
          </Card>
        ))}
      </div>
      <Banner tone="stone" title="Next interview script">
        <p>
          {retest.length
            ? `The next script will target ${retest.map((d) => d.hypothesis_id).join(", ")} and follow up on your strongest pain themes.`
            : "Every hypothesis has a firm verdict; the next script will dig deeper into your strongest pain themes."}{" "}
          Script generation and Markdown/PDF export are coming in the next build stage.
        </p>
      </Banner>
    </div>
  );
}
