# Time-Saved Report

This report separates what was **measured** from what is **estimated**. The
measurements come from the bundled sample sets in demo mode. The estimates
cover a realistic interview round with a local model. Each estimate states its
basis so it can be checked; replace it with your own timings when you have
them (see [How to measure it yourself](#how-to-measure-it-yourself)).

## The task

Synthesising a round of customer discovery interviews: reading the
transcripts, pulling out pain points with quotes, grouping them, judging each
hypothesis with evidence for and against, planning the next round of
questions, and writing it up for co-founders or mentors.

## Measured: the sample sets

| Sample set | Interviews | Words | Hypotheses | Model calls (extract + assess + cluster) |
| --- | --- | --- | --- | --- |
| Freelancers and late invoices | 6 | 1,461 | 4 | 6 + 6 + 1 |
| Physiotherapy clinics and no-shows | 5 | 909 | 4 | 5 + 5 + 1 |
| Restaurants and food waste | 3 | 457 | 3 | 3 + 3 + 1 |

A demo-mode run of the physiotherapy and freelance sets, plus reviewing,
approving and drafting a script for the freelance set, logged **25 model
calls and 21,950 tokens** (`python -m scripts.usage_report`). Everything Groundwork
does *around* the model (quote verification, frequency counts, verdict rules,
question linting, the Markdown/PDF export) took **0.1 s per analysis and
0.03 s for the script** in demo mode. In practice, all of the wait is model
time.

The sample transcripts are short (150 to 250 words each) so the demo stays
fast. A 45-minute interview is about 30 times longer, which is why the estimate
below uses a full-length round.

## Estimated: one realistic round

**Scenario:** 6 interviews of about 45 minutes (about 6,500 words, or 36,000
characters, each), 4 hypotheses, model `qwen2.5:7b` through Ollama.

**Model workload.** Transcripts are split into chunks of 6,000 characters
(`EXTRACTION_CHUNK_CHARS`), so each interview is about 6 chunks. Each chunk
gets one extraction call and one assessment call: 6 × 6 × 2 = 72 calls, plus
2 or 3 clustering calls and 1 script call, so **about 75 calls** of roughly
2,000 prompt tokens and 300 output tokens each.

| Hardware | Assumed speed (prompt / output) | Per call | Whole round |
| --- | --- | --- | --- |
| 6 GB GPU (e.g. RTX 3060 laptop) | ~1,000 / ~35 tokens per s | ~10 s | **~12 to 15 min** |
| Modern laptop CPU only | ~80 / ~7 tokens per s | ~70 s | **~1.5 h** (runs unattended) |

The speeds are typical figures for a 4-bit 7B model, not measurements from this
project.

| Step | Manual (estimate) | With Groundwork (estimate) | Basis |
| --- | --- | --- | --- |
| Read transcripts, extract pain points with exact quotes | 3 to 6 h | 12 to 15 min model time (GPU), unattended | 30 to 60 min per interview for careful coding and quoting, a common practitioner range |
| Group into themes, count distinct interviewees | 30 to 60 min | seconds | Done by code; no recounting after edits |
| Judge each hypothesis with evidence for and against | 30 to 60 min | 10 to 20 min of review | 2 to 5 min per hypothesis at the checkpoint, reading quotes and opening sources |
| Draft the next interview guide | 30 to 45 min | 5 to 10 min of editing | Draft targets only UNTESTED/MIXED hypotheses; bias check on each question |
| Write up a shareable summary with sources | 30 to 60 min | seconds | Markdown/PDF export with decision log |
| **Founder's time** | **5 to 10 h** | **15 to 30 min** | plus 12 to 15 min of model time on a GPU |

On these assumptions, a founder spends roughly **4.5 to 9.5 hours less** per
round of 6 interviews. Most of that is the extraction step. The review time
is kept on purpose (see below).

## What is gained beyond time

These follow from how the product works, not from estimates:

- Every quote shown is checked against the transcript; a manual synthesis
  usually paraphrases from memory.
- Contradicting evidence is always listed next to supporting evidence, and
  interviewees who never discussed a hypothesis are counted, not ignored.
- Frequencies count distinct interviewees, so one talkative person cannot
  make a theme look common.
- The decision log records what the AI suggested and what the founder decided,
  with reasons.

## What is not saved

- Doing the interviews themselves.
- Judgment at the checkpoint. Groundwork is built so the founder still reads
  the evidence; skipping that review would save time and lose the point.
- Checking quotes in context. Verification proves a quote exists, not that it
  was read in the right sense.

## How to measure it yourself

1. Take a set of your own interviews (or a sample set).
2. **Manual baseline:** time a hand synthesis: notes per interview, an
   affinity map of pain points, a verdict per hypothesis with quotes, the next
   interview guide and a short write-up.
3. **With Groundwork:** note the analysis time shown in the app (or from
   `python -m scripts.usage_report`: calls × average latency) and time your own
   review, script editing and export separately.
4. Replace the estimates above and record your hardware and model.
