// Thin typed client for the Groundwork API. Errors come back as ApiError with
// the backend's stable error code, so the UI can show a specific message.

import type {
  FinalDecision,
  Health,
  InterviewScript,
  LogEntry,
  QuestionEdit,
  ReviewInput,
  SampleSet,
  StatusResponse,
  Study,
  StudySummary,
  Transcript,
  UploadResult,
} from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const BASE = "/api";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(BASE + path, init);
  } catch {
    throw new ApiError(0, "network", "Cannot reach the Groundwork server. Is the backend running?");
  }
  if (resp.status === 204) return undefined as T;
  const body = await resp.json().catch(() => null);
  if (!resp.ok) {
    const err = body?.error;
    if (err?.message) throw new ApiError(resp.status, err.code ?? "error", err.message);
    // FastAPI request validation errors: {"detail": [{msg, loc}, ...]}
    const detail = Array.isArray(body?.detail)
      ? body.detail.map((d: { msg: string }) => d.msg).join("; ")
      : body?.detail;
    throw new ApiError(resp.status, "invalid_input", detail || `Request failed (${resp.status})`);
  }
  return body as T;
}

function json<T>(method: string, path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export const api = {
  health: () => request<Health>("/health"),
  samples: () => request<SampleSet[]>("/samples"),
  studies: () => request<StudySummary[]>("/studies"),
  study: (id: string) => request<Study>(`/studies/${id}`),
  status: (id: string) => request<StatusResponse>(`/studies/${id}/status`),
  createStudy: (name: string, hypotheses: string[] = []) =>
    json<Study>("POST", "/studies", { name, hypotheses }),
  createFromSample: (setId: string) => json<Study>("POST", `/studies/from-sample/${setId}`),
  setHypotheses: (id: string, hypotheses: string[]) =>
    json<Study>("PUT", `/studies/${id}/hypotheses`, { hypotheses }),
  upload: (id: string, files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return request<UploadResult>(`/studies/${id}/interviews`, { method: "POST", body: form });
  },
  paste: (id: string, text: string, title: string) =>
    json<UploadResult>("POST", `/studies/${id}/interviews/text`, { text, title }),
  transcript: (id: string, interviewId: string) =>
    request<Transcript>(`/studies/${id}/interviews/${encodeURIComponent(interviewId)}`),
  removeInterview: (id: string, interviewId: string) =>
    request<void>(`/studies/${id}/interviews/${encodeURIComponent(interviewId)}`, {
      method: "DELETE",
    }),
  analyze: (id: string) => json<StatusResponse>("POST", `/studies/${id}/analyze`),
  review: (id: string, hypothesisId: string, input: ReviewInput) =>
    json<Study>("PUT", `/studies/${id}/reviews/${hypothesisId}`, input),
  approve: (id: string, acknowledgeSmallSample: boolean) =>
    json<Study>("POST", `/studies/${id}/approve`, {
      acknowledge_small_sample: acknowledgeSmallSample,
    }),
  reopen: (id: string, reason: string) => json<Study>("POST", `/studies/${id}/reopen`, { reason }),
  decisions: (id: string) => request<FinalDecision[]>(`/studies/${id}/decisions`),
  decisionLog: (id: string) => request<LogEntry[]>(`/studies/${id}/decision-log`),
  script: (id: string) => request<InterviewScript>(`/studies/${id}/script`),
  generateScript: (id: string) => json<InterviewScript>("POST", `/studies/${id}/script`),
  saveScript: (id: string, questions: QuestionEdit[]) =>
    json<InterviewScript>("PUT", `/studies/${id}/script`, { questions }),
};

/** Download URL of the approved study's report (served as an attachment). */
export function reportUrl(id: string, format: "md" | "pdf"): string {
  return `${BASE}/studies/${id}/report.${format}`;
}
