# Architecture

Groundwork is a FastAPI backend with a React frontend. One rule shapes the
design: **the language model proposes, code decides, the founder approves.**
The model only reads text and proposes quotes, groupings, stances and
question wording. Code checks every quote against the transcript, counts
frequencies, applies the verdict rules and lints the questions. Nothing after
the human checkpoint runs until the founder has approved every verdict.

## Pipeline

```mermaid
flowchart TD
    U[Founder: transcripts + hypotheses] --> P[Parse txt / md / pdf / docx<br/>optional name redaction]
    P --> S[Segment into speaker turns<br/>numbered segments with exact offsets]
    S --> E[Extract pain points per chunk<br/>LLM, hypothesis-blind]
    E --> V{Verify each quote<br/>exact or fuzzy ≥ 0.92}
    V -- not found --> R[Rejected: logged, never shown]
    V -- verified --> C[Cluster into themes<br/>LLM map-reduce, IDs policed by code]
    C --> F[Frequency = distinct interviewees<br/>code]
    S --> A[Assess each interview × hypothesis<br/>LLM stance + quotes]
    A --> V2{Verify quotes<br/>downgrade unbacked stances}
    V2 --> D[Verdict rules<br/>VALIDATED / INVALIDATED / MIXED / UNTESTED<br/>confidence, what would change it]
    F --> X
    D --> X[[HUMAN CHECKPOINT<br/>accept / change / reject each verdict<br/>remove quotes, add notes]]
    X -- approved --> Q[Next interview script<br/>targets chosen by code, wording by LLM,<br/>leading-question linter]
    X -- approved --> O[Export Markdown / PDF<br/>with decision log + AI usage]
    X -. every edit .-> L[(Append-only decision log)]
```

## Components

```mermaid
flowchart LR
    subgraph Browser
        UI[React + Vite + Tailwind<br/>4-step flow, source panel]
    end
    subgraph Backend [FastAPI]
        API[REST API<br/>/api/studies/...]
        RUN[Background analysis runner]
        SVC[Services: segmentation, verification,<br/>extraction, clustering, assessment,<br/>verdicts, review, script, report]
        LLM[LLMProvider interface]
        DB[(SQLite: studies, reviews,<br/>decision log, LLM calls, scripts)]
    end
    UI -- /api --> API
    API --> RUN --> SVC
    API --> SVC
    SVC --> LLM
    API --> DB
    RUN --> DB
    LLM --> OL[Ollama<br/>qwen2.5:7b / llama3.1:8b<br/>local, default]
    LLM --> GQ[Groq free tier<br/>optional]
    LLM --> DM[Demo replay<br/>hand labels, no model]
```

## Key decisions

| Decision | Why |
| --- | --- |
| Hypothesis-blind extraction | The model looks for pain without knowing what the founder hopes to find, which limits confirmation bias. |
| Quotes verified against the transcript | Small local models paraphrase and invent. Only text found in the transcript (exact, or fuzzy ≥ 0.92 with numbers and negations unchanged) is shown as evidence, always with interview, speaker and segment. |
| Verdicts by rules, not by the model | Rules are inspectable and stable: ≥ 2 interviewees and ≥ 75% agreement to validate or invalidate, never from a single interview, confidence capped below 5 interviews. The UI shows the rule and what would change the verdict. |
| Checkpoint enforced on the server | `require_approved` guards the script, the decisions and the export (409 otherwise). The disabled button in the UI is a convenience, not the gate. |
| Structured output with repair | JSON schema sent to the model (Ollama `format`), Pydantic validation, up to 2 retries with the validation errors fed back. |
| Versioned prompts | `backend/prompts/<name>.v<N>.md`. Every logged call records the prompt version. |
| Deterministic settings | Temperature 0.1, fixed seed, concurrency 1 by default (one local GPU). |
| SQLite with JSON columns | One file, no server. Analysis results are stored whole as validated Pydantic models. |

## Data model

- `studies`: name, status (`draft → analyzing → awaiting_review → approved`,
  or `failed`), hypotheses, transcripts, analysis result.
- `reviews`: the founder's current decision per hypothesis.
- `decision_log`: append-only; every AI result and founder edit with a
  before/after snapshot and a timestamp.
- `llm_calls`: provider, model, prompt version, tokens, latency, success.
- `scripts`: the next interview script (discarded when the review is reopened).

## Failure states

| Situation | What the user sees |
| --- | --- |
| Model server unreachable | "The language model could not be reached", with the command to start Ollama. |
| Model not pulled / key missing | "The language model is not set up", with `ollama pull ...`. |
| Model keeps returning invalid JSON | That chunk is skipped and listed in a warning. If every interview fails, the analysis fails ("The model kept returning unusable answers") instead of showing empty results. |
| Empty or unusable transcript | Rejected on upload with the reason. |
| Fewer than 5 interviews | Warning everywhere; confidence capped at LOW; approval needs an explicit acknowledgement. |
| Single interview supports a hypothesis | Never VALIDATED; at most MIXED or UNTESTED. |
| Server restart mid-analysis | Study marked failed ("interrupted"), can be re-run. |
