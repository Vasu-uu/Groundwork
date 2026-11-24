# Time-Saved Report

> Template. Replace the bracketed values with your own measurements. The
> estimates below are assumptions to be checked, not results.

## The task

Synthesising a round of customer discovery interviews: reading transcripts,
pulling out pain points with quotes, grouping them, judging each hypothesis,
and planning the next round of questions.

## Method

1. Pick one sample set (or your own interviews) with N interviews.
2. **Manual baseline:** time yourself doing the synthesis by hand: notes per
   interview, an affinity map of pain points, a verdict per hypothesis with
   supporting quotes, and the next interview guide.
3. **With Groundwork:** time the whole flow, including the analysis run on your
   hardware and your review at the checkpoint (reading the evidence, opening
   sources, editing verdicts and questions).
4. Note the quality checks: did the manual synthesis cite quotes for every
   claim? Did it record contradicting evidence?

## Results

| Step | Manual | With Groundwork | Notes |
| --- | --- | --- | --- |
| Read transcripts and extract pain points with quotes | [__ min] | [__ min model time] | Model time depends on hardware (CPU vs GPU). |
| Group into themes and count interviewees | [__ min] | [seconds] | Counting is done by code. |
| Judge each hypothesis with evidence for and against | [__ min] | [__ min review] | The founder's review time is the important part. |
| Draft the next interview guide | [__ min] | [__ min edit] | Includes fixing flagged questions. |
| Write up a shareable summary | [__ min] | [seconds] | Markdown / PDF export. |
| **Total** | **[__ min]** | **[__ min]** | |

Hardware for the Groundwork timing: [CPU / GPU, RAM], model [qwen2.5:7b Q4].

## What is not saved

- Doing the interviews themselves.
- Judgment at the checkpoint: Groundwork is designed so the founder still reads
  the evidence. Skipping that review would save time and lose the point.

## Assumptions to verify

- A founder spends about 30 to 60 minutes per interview on careful synthesis
  (re-reading, coding, quoting). [check against your own baseline]
- Review at the checkpoint takes about 2 to 5 minutes per hypothesis.
  [measure]
