import type { Evidence, HypothesisVerdict, Study } from "../api/types";

export function evidence(over: Partial<Evidence> = {}): Evidence {
  const e = {
    interview_id: "I-01",
    segment: 4,
    speaker: "Maya",
    role: "interviewee" as const,
    quote: "I spend every Friday chasing invoices.",
    start: 100,
    end: 138,
    match: "exact" as const,
    score: 1,
    paraphrase: false,
    ...over,
  };
  return { ...e, key: `${e.interview_id}:${e.start}:${e.end}` };
}

export function verdict(id: string, over: Partial<HypothesisVerdict> = {}): HypothesisVerdict {
  const supporting = [evidence({ interview_id: "I-01" }), evidence({ interview_id: "I-02", start: 10, end: 40 })];
  const contradicting = [evidence({ interview_id: "I-03", quote: "Clients pay me on time.", start: 5, end: 28 })];
  return {
    hypothesis: { id, text: `Hypothesis ${id}` },
    verdict: "VALIDATED",
    confidence: "medium",
    confidence_note: "Most interviewees who discussed it agreed.",
    what_would_change: "Two more contradicting interviews would make it MIXED.",
    rule: "VALIDATED when at least 2 support and 75% agree.",
    counts: { supports: 2, contradicts: 1, mixed: 0, not_discussed: 3 },
    provisional: false,
    supporting,
    contradicting,
    assessments: [],
    related_theme_ids: [],
    status: "ai_suggestion",
    counter_evidence: contradicting,
    ...over,
  };
}

export function study(over: Partial<Study> = {}): Study {
  const verdicts = [verdict("H1"), verdict("H2", { verdict: "UNTESTED" })];
  return {
    id: "s1",
    name: "Freelancers",
    status: "awaiting_review",
    progress: "done",
    error: null,
    error_kind: null,
    sample_set: null,
    created_at: "2026-11-24T10:00:00Z",
    updated_at: "2026-11-24T10:05:00Z",
    analyzed_at: "2026-11-24T10:05:00Z",
    approved_at: null,
    hypotheses: verdicts.map((v) => v.hypothesis),
    interviews: [],
    corpus_warnings: [],
    small_sample: false,
    result: {
      run_id: "r1",
      interview_count: 6,
      warnings: [],
      pain_points: [],
      rejected_quotes: [],
      quote_stats: { proposed: 10, exact: 8, fuzzy: 1, rejected: 1, verified: 9, rate: 0.9 },
      clustering: { themes: [], unclustered: [], method: "llm", dropped_ids: [], notes: [] },
      verdicts,
      failures: [],
      prompt_ids: [],
    },
    reviews: {},
    checkpoint: { total: 2, reviewed: 0, missing: ["H1", "H2"], approved: false, can_approve: false, needs_small_sample_ack: false },
    usage: {
      run_id: "r1",
      calls: 12,
      failed_calls: 0,
      prompt_tokens: 1000,
      completion_tokens: 200,
      total_tokens: 1200,
      cost_eur: 0,
      providers: ["mock"],
      models: ["mock"],
    },
    cost_label: "0 EUR, 1 200 tokens",
    ...over,
  };
}
