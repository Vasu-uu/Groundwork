# Responsible AI

## Local first

The default provider is [Ollama](https://ollama.com) with an open-weight model
(`qwen2.5:7b` or `llama3.1:8b`). Interviews, analyses and decisions stay on the
founder's machine, in a local SQLite file. No account, no telemetry, no paid
API. The optional Groq provider sends transcript text to Groq's servers; use it
only with interviews you are allowed to share, and only on its free tier.

## Personal data

Customer interviews contain personal data: names, employers, sometimes health
or financial details (the physiotherapy sample is about patients).

- The upload screen reminds founders to remove what they do not need.
- **Optional name redaction** replaces speaker names and the
  `participant`/`interviewer` front-matter names with "Participant" and
  "Interviewer" everywhere in the transcript, before anything is stored or sent
  to a model. It does **not** detect other names in the text (a colleague, a
  client company, "Anna at reception"); the app says so after redacting.
- Founders should get consent before recording interviews and follow GDPR or
  local rules on storing transcripts. Deleting a study (home page) removes its
  interviews, decisions, log and call records from the database.
- All bundled sample interviews are fictional.

## Limitations

- **Small models make mistakes.** A 7B model misses pain points, misreads
  stances and paraphrases quotes. Groundwork verifies every quote and drops
  unbacked stances, but it cannot detect a real quote used out of context.
  That is why the founder reviews every verdict and can remove quotes.
- **Verdicts are only as good as the interviews.** Leading questions produce
  agreeable answers. The assessment prompt treats a bare "yes" to a leading
  question as weak, and the script linter helps with the next round, but it
  cannot fix interviews that were already biased.
- **Small samples.** Below 5 interviews every finding is provisional, and
  confidence is capped. Three interviews cannot validate a market.
- **Founder notes are paraphrases.** They are marked as such and carry less
  weight; they are the founder's memory, not the customer's words.
- **English only.** Prompts, the linter and the fuzzy matching assume English.
- **PDF export** uses built-in fonts: characters outside Western European
  languages are replaced. The Markdown export keeps them.

## Bias

| Risk | Mitigation |
| --- | --- |
| Confirmation bias (founder and model see what they hope) | Hypothesis-blind extraction; contradicting quotes shown side by side with supporting ones; devil's advocate toggle; MIXED and UNTESTED are first-class verdicts. |
| Loud interviewees dominating | Frequency counts distinct interviewees, not quotes. |
| Over-confidence from few voices | Never VALIDATED from a single interview; confidence capped below 5 interviews; "what would change this verdict" shown. |
| Leading questions in the next round | Each question has a bias check; rules flag leading, hypothetical, loaded and closed wording, including founder edits. |
| Model's own leanings | Low temperature, fixed seed, verdicts computed by rules, and an eval harness with hand labels to measure agreement. |
| Sampling bias (who was interviewed) | Not solved by software. The report shows how many interviewees discussed each hypothesis; the founder decides whether the sample is representative. |

## Known failure cases

- A model that returns invalid JSON repeatedly: that chunk is skipped and
  listed in the results; if every interview fails, the analysis fails with a
  clear message instead of showing empty results as findings.
- Transcripts without speaker labels are treated as founder notes
  (paraphrase), which lowers their weight. Label speakers ("Interviewer:",
  "Maya:") to avoid this, and check the speaker list shown after upload.
- Sarcasm and irony are hard for small models and may flip a stance. The
  per-interview table in "How this was decided" makes these visible.
- Demo mode replays hand labels: it shows how the product works, not how well
  a model performs. Use the eval harness with a real model for that.
