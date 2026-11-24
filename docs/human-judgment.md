# Human judgment

Groundwork helps a founder think; it does not decide for them. These are the
places where a person, not the model, has the last word.

## 1. The human checkpoint (step 3)

After the analysis, every hypothesis verdict is labelled **AI suggestion**.
The founder reviews each one:

- **Accept** the suggestion as it is;
- **Change** it to another verdict, with a written reason (required);
- **Reject** it as untrustworthy, with a reason, so the hypothesis is
  re-tested in the next interview;
- **Remove quotes** they think were misread or taken out of context. The
  screen then shows what the verdict rules would say without those quotes, so
  the founder sees the effect of their own edit;
- add a **note**.

"Approve and continue" stays disabled until every verdict is reviewed, and
with fewer than 5 interviews the founder must also confirm that the results
are provisional. The server enforces the same rules: the next interview script,
the approved decisions and the export all return `409 checkpoint_required`
until the study is approved. Nothing is ever auto-approved.

Reopening an approved review is allowed (the reason is logged) and discards
the interview script drafted from the earlier decisions.

## 2. Everything downstream uses the founder's decisions

The next interview script targets the hypotheses the founder marked UNTESTED,
MIXED or re-test, not the AI's labels. The founder's reasoning is passed to the
model as context. The export shows the founder's verdict first and the AI
suggestion next to it when they differ.

## 3. Showing uncertainty instead of hiding it

Each verdict comes with:

- a confidence level and a plain note explaining it (capped at LOW below 5
  interviews);
- **what would change this verdict**, quantified ("1 more interview
  contradicting it would turn this into MIXED");
- the per-interview stances, so the founder can see who said what;
- the exact rule that produced the verdict.

The **devil's advocate** toggle puts the strongest evidence against each
hypothesis at the top. When nobody contradicted a hypothesis, it says how many
interviewees never discussed it, because silence is not support.

## 4. The interview script stays editable

Every drafted question shows its purpose and a bias check. Rules flag leading,
hypothetical, pitching, closed, loaded, double-barrelled or long questions,
including questions the founder writes or edits. If the model skips a target,
the founder gets a placeholder to fill in rather than a silent gap.

## 5. An audit trail

The decision log is append-only. It records the AI's results (with the prompt
versions used), every review edit with before and after values, approvals,
reopenings and script changes, each with a timestamp. It is part of the export.
