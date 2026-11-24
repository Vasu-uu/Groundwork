# Sample interview sets

Three **fictional, anonymized** interview sets used for the demo mode, the
tests and the eval harness. All people, businesses and numbers are invented;
any resemblance to real people is coincidental.

| Set | Interviews | Formats | Purpose |
| --- | --- | --- | --- |
| [`freelance-invoicing`](freelance-invoicing) | 6 | markdown, timestamped text, Q&A, founder notes | Main demo |
| [`physio-no-shows`](physio-no-shows) | 5 | markdown, timestamped text, plain labels, notes | Second domain |
| [`restaurant-waste`](restaurant-waste) | 3 | markdown, plain text | Triggers the "fewer than 5 interviews" warning |

## Layout of a set

```
<set>/
  set.json        name, description and the founder's hypotheses
  labels.json     hand-labelled ground truth (pain points with verbatim quotes, expected verdicts)
  interviews/     one file per interview (.md or .txt)
```

Each interview may start with a `---` front-matter block (`id`, `participant`,
`persona`, `date`). Speaker turns use any of these layouts:

```
**Interviewer:** How do you get paid?
[00:01:02] Tomas: Mostly bank transfer.
Q: ... / A: ...
Interviewer: ... / Sofia: ...
```

Files without speaker labels (bullet notes) are parsed as founder notes and
flagged as paraphrase rather than verbatim speech.

Every hypothesis in a set has one expected verdict in `labels.json`, and every
quote in `labels.json` is a verbatim substring of its transcript; the test
suite checks this.
