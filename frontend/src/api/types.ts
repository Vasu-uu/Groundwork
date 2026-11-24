// Types mirroring the backend's Pydantic response models (backend/app/api/schemas.py
// and backend/app/models). Keep them in sync when the API changes.

export type Verdict = "VALIDATED" | "INVALIDATED" | "MIXED" | "UNTESTED";
export type Confidence = "low" | "medium" | "high";
export type Stance = "supports" | "contradicts" | "mixed" | "not_discussed";
export type Role = "interviewer" | "interviewee" | "note";
export type Intensity = "low" | "medium" | "high";
export type StudyStatus = "draft" | "analyzing" | "awaiting_review" | "approved" | "failed";
export type Decision = "approve" | "change" | "reject";

export interface Hypothesis {
  id: string;
  text: string;
}

export interface Evidence {
  interview_id: string;
  segment: number;
  speaker: string;
  role: Role;
  quote: string;
  start: number;
  end: number;
  match: "exact" | "fuzzy";
  score: number;
  key: string;
  paraphrase: boolean;
}

export interface PainPoint {
  id: string;
  interview_id: string;
  summary: string;
  intensity: Intensity;
  evidence: Evidence;
}

export interface RejectedQuote {
  interview_id: string;
  claimed_segment: number | null;
  quote: string;
  summary: string;
  reason: string;
  best_score: number;
}

export interface VerificationStats {
  proposed: number;
  exact: number;
  fuzzy: number;
  rejected: number;
  verified: number;
  rate: number;
}

export interface Theme {
  id: string;
  label: string;
  description: string;
  pain_point_ids: string[];
  interview_ids: string[];
  frequency: number;
  share: number;
  top_intensity: Intensity;
  paraphrase_only: boolean;
}

export interface Clustering {
  themes: Theme[];
  unclustered: string[];
  method: "llm" | "fallback";
  dropped_ids: string[];
  notes: string[];
}

export interface InterviewAssessment {
  interview_id: string;
  hypothesis_id: string;
  stance: Stance;
  rationale: string;
  supporting: Evidence[];
  contradicting: Evidence[];
  downgraded_from: Stance | null;
}

export interface StanceCounts {
  supports: number;
  contradicts: number;
  mixed: number;
  not_discussed: number;
}

export interface HypothesisVerdict {
  hypothesis: Hypothesis;
  verdict: Verdict;
  confidence: Confidence;
  confidence_note: string;
  what_would_change: string;
  rule: string;
  counts: StanceCounts;
  provisional: boolean;
  supporting: Evidence[];
  contradicting: Evidence[];
  assessments: InterviewAssessment[];
  related_theme_ids: string[];
  status: "ai_suggestion";
  counter_evidence: Evidence[];
}

export interface AnalysisResult {
  run_id: string;
  interview_count: number;
  warnings: string[];
  pain_points: PainPoint[];
  rejected_quotes: RejectedQuote[];
  quote_stats: VerificationStats;
  clustering: Clustering;
  verdicts: HypothesisVerdict[];
  failures: string[];
  prompt_ids: string[];
}

export interface InterviewSummary {
  id: string;
  title: string;
  participant: string | null;
  format: "dialogue" | "notes";
  source_filename: string | null;
  segments: number;
  customer_segments: number;
  warnings: string[];
}

export interface Review {
  hypothesis_id: string;
  decision: Decision;
  ai_verdict: Verdict;
  final_verdict: Verdict | null;
  reasoning: string;
  removed_evidence: string[];
  note: string;
  reviewed_at: string;
  recomputed_ai_verdict: Verdict;
}

export interface Checkpoint {
  total: number;
  reviewed: number;
  missing: string[];
  approved: boolean;
  can_approve: boolean;
  needs_small_sample_ack: boolean;
}

export interface Usage {
  run_id: string;
  calls: number;
  failed_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_eur: number;
  providers: string[];
  models: string[];
}

export interface Study {
  id: string;
  name: string;
  status: StudyStatus;
  progress: string | null;
  error: string | null;
  error_kind: string | null;
  sample_set: string | null;
  created_at: string;
  updated_at: string;
  analyzed_at: string | null;
  approved_at: string | null;
  hypotheses: Hypothesis[];
  interviews: InterviewSummary[];
  corpus_warnings: string[];
  small_sample: boolean;
  result: AnalysisResult | null;
  reviews: Record<string, Review>;
  checkpoint: Checkpoint;
  usage: Usage;
  cost_label: string;
}

export interface StudySummary {
  id: string;
  name: string;
  status: StudyStatus;
  sample_set: string | null;
  created_at: string;
  interviews: number;
  hypotheses: number;
}

export interface StatusResponse {
  status: StudyStatus;
  progress: string | null;
  error: string | null;
  error_kind: string | null;
  usage: Usage;
  cost_label: string;
}

export interface SampleSet {
  id: string;
  name: string;
  description: string;
  interview_count: number;
}

export interface Segment {
  number: number;
  turn: number;
  speaker: string;
  role: Role;
  text: string;
  start: number;
  end: number;
}

export interface Transcript {
  id: string;
  title: string;
  source_filename: string | null;
  format: "dialogue" | "notes";
  text: string;
  metadata: Record<string, string>;
  participant: string | null;
  segments: Segment[];
  warnings: string[];
}

export interface UploadResult {
  added: InterviewSummary[];
  errors: { filename: string; error: string }[];
}

export interface Health {
  status: "ok" | "degraded";
  version: string;
  llm: {
    provider: string;
    model: string;
    status: "ok" | "model_missing" | "unreachable" | "misconfigured";
    detail: string;
    hint: string | null;
    ok: boolean;
  };
  cost_eur: number;
}

export interface LogEntry {
  id: number;
  at: string;
  actor: "founder" | "ai" | "system";
  action: string;
  hypothesis_id: string | null;
  details: Record<string, unknown>;
}

export interface FinalDecision {
  hypothesis_id: string;
  text: string;
  ai_verdict: Verdict;
  final_verdict: Verdict | null;
  decision: Decision;
  reasoning: string;
  note: string;
  supporting: Evidence[];
  contradicting: Evidence[];
}

export interface ReviewInput {
  decision: Decision;
  verdict?: Verdict | null;
  reasoning?: string;
  removed_evidence?: string[];
  note?: string;
}
