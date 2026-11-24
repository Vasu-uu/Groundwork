import type { Confidence, Stance, Verdict } from "../api/types";

export const VERDICT_STYLE: Record<Verdict, string> = {
  VALIDATED: "bg-emerald-50 text-emerald-800 ring-emerald-600/25",
  INVALIDATED: "bg-rose-50 text-rose-800 ring-rose-600/25",
  MIXED: "bg-amber-50 text-amber-900 ring-amber-600/30",
  UNTESTED: "bg-stone-100 text-stone-700 ring-stone-500/25",
};

export const VERDICT_HELP: Record<Verdict, string> = {
  VALIDATED: "Most interviewees who discussed it support it",
  INVALIDATED: "Most interviewees who discussed it contradict it",
  MIXED: "Evidence points both ways",
  UNTESTED: "Not enough interviews discussed it",
};

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  low: "Low confidence",
  medium: "Medium confidence",
  high: "High confidence",
};

export const STANCE_LABEL: Record<Stance, string> = {
  supports: "supports",
  contradicts: "contradicts",
  mixed: "mixed",
  not_discussed: "not discussed",
};

export const PROGRESS_STEPS = [
  { key: "extracting", label: "Extracting pain points and verifying quotes" },
  { key: "clustering", label: "Grouping pain points into themes" },
  { key: "assessing", label: "Checking each hypothesis interview by interview" },
  { key: "deciding", label: "Applying the verdict rules" },
] as const;

/** User-facing explanation and next action for each analysis failure kind. */
export const FAILURE_HELP: Record<string, { title: string; action: string }> = {
  provider_unavailable: {
    title: "The language model could not be reached",
    action: "Start Ollama (`ollama serve`) or check your network, then run the analysis again.",
  },
  provider_config: {
    title: "The language model is not set up",
    action: "Pull the model (`ollama pull qwen2.5:7b`) or check your API key in .env.",
  },
  model_output: {
    title: "The model kept returning unusable answers",
    action: "Run the analysis again, or try a larger model.",
  },
  invalid_input: {
    title: "There is nothing to analyse",
    action: "Add interviews with customer speech and at least one hypothesis.",
  },
  interrupted: {
    title: "The server restarted during the analysis",
    action: "Run the analysis again.",
  },
  internal: {
    title: "Something went wrong on our side",
    action: "Check the backend log, then try again.",
  },
};

export const ALL_VERDICTS: Verdict[] = ["VALIDATED", "INVALIDATED", "MIXED", "UNTESTED"];
