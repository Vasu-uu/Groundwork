# Groundwork

**Evidence-first customer discovery copilot for early-stage founders.**
Entry for the *AI Agents for Founders Challenge (HETIC 2026)*.

Paste or upload customer interview transcripts, state your hypotheses, and
Groundwork extracts pain points tied to verbatim, verified quotes, clusters
them into themes, and suggests a verdict for each hypothesis. You review every
verdict at a human checkpoint before it drafts your next interview script.

> Status: work in progress (Stage 6 of 8: web app with the four-step flow and the review checkpoint).
> API docs at http://localhost:8000/docs once `uvicorn app.main:app` is running.
>
> From `backend/`: `python -m scripts.segment --set freelance-invoicing` previews parsing;
> `python -m scripts.extract --set ...` runs pain-point extraction ("verified quotes: X/Y");
> `python -m scripts.analyze --set ...` runs the full analysis with your model.
> Sample data is described in [samples/README.md](samples/README.md).

## Free by design

All runtime models are free: an open-weight model through
[Ollama](https://ollama.com) by default (data never leaves your machine), or an
optional free-tier hosted API (Groq) for deployed demos. No paid APIs.

## Quick start (backend, manual)

Requires Python 3.11+ and, for the default provider, Ollama.

```bash
ollama pull qwen2.5:7b          # ~4.7 GB, fits a 6 GB GPU; runs on CPU too
cp .env.example .env            # adjust if needed
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows; use `source .venv/bin/activate` elsewhere
pip install -e ".[dev]"
python -m scripts.check_llm     # one-shot provider smoke test
uvicorn app.main:app --reload   # then open http://localhost:8000/api/health
pytest                          # run the test suite
```

## Quick start (web app, manual)

Requires Node.js 20+. Start the backend first (above), then:

```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173, proxies /api to localhost:8000
npm test                        # component and unit tests (Vitest)
```

Set `GROUNDWORK_API` to point the dev proxy at a backend on another address.

The app walks through four steps: **1** add interviews and hypotheses and run
the analysis; **2** read pain themes and the AI-suggested verdicts, with
supporting and contradicting quotes side by side (click any quote to see it
highlighted in its transcript; toggle *devil's advocate* for the strongest
evidence against); **3** the human checkpoint, where you accept, change or
reject each verdict and remove misread quotes ("Approve and continue" stays
disabled until every verdict is reviewed); **4** your approved decisions, which
drive the next interview script.

## API overview

| Endpoint | Purpose |
| --- | --- |
| `POST /api/studies` / `POST /api/studies/from-sample/{set}` | Create a study (blank or from sample data) |
| `POST /api/studies/{id}/interviews` (multipart) / `.../interviews/text` | Add interviews (txt, md, pdf, docx, or pasted text) |
| `PUT /api/studies/{id}/hypotheses` | Set the hypotheses to test |
| `POST /api/studies/{id}/analyze`, `GET .../status` | Run the analysis in the background and poll progress |
| `PUT /api/studies/{id}/reviews/{hypothesis}` | **Human checkpoint**: approve, change (with reason) or reject each verdict, remove quotes, add notes |
| `POST /api/studies/{id}/approve` / `.../reopen` | Pass the checkpoint (refused until every verdict is reviewed) or reopen it |
| `GET /api/studies/{id}/decisions` | Approved decisions; returns `409 checkpoint_required` before approval |
| `GET /api/studies/{id}/decision-log` | Append-only log of AI suggestions and founder decisions with timestamps |

## Configuration

All settings come from environment variables; see [`.env.example`](.env.example).

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `ollama` | `ollama`, `groq` or `mock` |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Any pulled Ollama model (`llama3.1:8b` also works) |
| `OLLAMA_FORCE_CPU` | `false` | Force CPU inference when the GPU is too small |
| `GROQ_API_KEY` | (empty) | Free-tier key, only for `LLM_PROVIDER=groq` |
| `LLM_TEMPERATURE` / `LLM_SEED` | `0.1` / `42` | Deterministic generation |

## License

[MIT](LICENSE)
