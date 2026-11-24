# AI Disclosure Statement

> Template. The runtime section is filled from Groundwork's own call log with
> `python -m scripts.usage_report` (from `backend/`). Fill in the development
> section yourself before submitting.

## 1. AI inside the product (runtime)

| | |
| --- | --- |
| Models | Open-weight models through Ollama, run locally: `qwen2.5:7b` (default) or `llama3.1:8b`. Optional: Groq free tier (`llama-3.1-8b-instant`). |
| Cost | 0 EUR. No paid APIs, credits or subscriptions. |
| What the model does | Proposes pain points with quotes, groups them into themes, states each interviewee's stance on each hypothesis with quotes, and drafts the wording of interview questions. |
| What the model does not do | Decide verdicts (rules in `backend/app/services/verdicts.py`), count frequencies, choose what the next interview targets, or approve anything. |
| Safeguards | Every quote verified against the transcript; unverified quotes are never shown. Structured output validated with retries. Prompts versioned in `backend/prompts/`. Human checkpoint enforced on the server. Rule-based question linter. |
| Logging | Every call is stored with provider, model, prompt version, tokens, latency and success, and summarised in each exported report. |

### Usage from the logs

Paste the output of `python -m scripts.usage_report` here, for example:

```
| Provider | Model | Prompt | Calls | Failed | Prompt tokens | Completion tokens | Avg latency |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ollama | qwen2.5:7b | extract_pain_points.v1 | ... | ... | ... | ... | ... |
| ollama | qwen2.5:7b | cluster_pain_points.v1 | ... | ... | ... | ... | ... |
| ollama | qwen2.5:7b | assess_hypotheses.v1 | ... | ... | ... | ... | ... |
| ollama | qwen2.5:7b | draft_interview_script.v1 | ... | ... | ... | ... | ... |
```

### Measured quality

Paste the output of `python -m evals.run_eval --out evals/results/<model>.md`
(quote verification rate, verdict agreement, stance agreement, pain-quote
recall on the three hand-labelled sample sets).

## 2. AI used to build the product (development)

_To be completed by the team: which AI tools were used during development, for
what (code, tests, documentation, sample data), and how their output was
reviewed._

## 3. Data

All sample interviews are fictional and written for this project. No real
customer data was used for development or evaluation.
