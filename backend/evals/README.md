# Eval harness

Three fictional sample sets in [`samples/`](../../samples) come with hand labels
(`labels.json`): the pain points with verbatim quotes, each interviewee's
stance on each hypothesis with quotes, and the expected verdict per hypothesis.
The harness runs the full analysis on each set and scores it against them.

```bash
cd backend
python -m evals.run_eval                          # the model in your .env (Ollama by default)
python -m evals.run_eval --provider demo          # self-check of the pipeline, no model
python -m evals.run_eval --out evals/results/qwen2.5-7b.md
```

## Metrics

| Metric | Meaning |
| --- | --- |
| Verified quotes | Quotes the model proposed that were found in the transcript (exact or fuzzy ≥ 0.92). Unverified quotes are dropped and never shown as evidence. |
| Verdict agreement | AI-suggested verdict equals the hand-labelled verdict. |
| Stance agreement | Per interview and hypothesis, the model's stance (after quote verification) equals the label. |
| Pain-quote recall | Share of labelled pain-point quotes recovered as verified evidence (same interview, overlapping span). |
| Calls, tokens, time | From the usage tracker. Cost is always 0 EUR. |

## Results

- [`results/demo-replay.md`](results/demo-replay.md): the `demo` provider
  replays the labels, so this checks the deterministic parts (quote
  verification, frequency counting, verdict rules), not a model. It scores 100%
  everywhere except one verdict, which is informative: on `restaurant-waste`
  H3, two of three interviewees support the hypothesis. The human label says
  VALIDATED; Groundwork's rule needs at least 75% agreement and says MIXED.
  The rule is deliberately conservative with tiny samples, and the human
  checkpoint is where a founder can overrule it, with a reason.
- Model results: run the harness with your local model and save the report
  under `results/`. Results depend on the model, its quantisation and the
  hardware, so they are not checked in as a claim.

The fixed seed and low temperature make runs repeatable on the same machine,
but not across model versions.
