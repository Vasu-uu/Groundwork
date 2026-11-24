"""Rule-based checks for leading or low-quality interview questions.

The model writes a "bias check" for each question, but a model can be wrong
about its own wording. These deterministic rules flag the common failure modes
of discovery questions so the founder sees them before the interview.
Each rule returns a short, actionable message.
"""

from __future__ import annotations

import re

_LEADING = re.compile(
    r"\b(don'?t you|doesn'?t it|wouldn'?t you|wouldn'?t it|isn'?t it|aren'?t you|"
    r"do you agree|would you agree|surely)\b|,\s*right\s*\?",
    re.IGNORECASE,
)
_HYPOTHETICAL = re.compile(
    r"\b(would you|could you see yourself|will you|if there (were|was)|imagine|"
    r"how much would|would it help|would you be willing)\b",
    re.IGNORECASE,
)
_CLOSED_START = re.compile(
    r"^\s*(do|does|did|are|is|was|were|have|has|can|could|should|will)\s+(you|they|it|your)\b",
    re.IGNORECASE,
)
_LOADED = re.compile(
    r"\b(frustrat\w*|annoy\w*|painful|pain|hate|struggle\w*|nightmare|waste of time|"
    r"terrible|awful|amazing|love)\b",
    re.IGNORECASE,
)
_PITCH = re.compile(r"\b(our (product|app|tool|solution)|a tool that|an app that)\b", re.IGNORECASE)

MAX_WORDS = 35

# Polite openers that make an otherwise open question look closed:
# "Can you walk me through..." is fine.
_OPEN_AFTER_CLOSED = re.compile(
    r"^\s*(can|could) you (tell|walk|describe|share|show)", re.IGNORECASE
)


def lint_question(text: str) -> list[str]:
    """Problems with one question's wording (empty list: no problem found)."""
    q = " ".join(text.split())
    if not q:
        return ["Empty question."]
    issues: list[str] = []
    if _LEADING.search(q):
        issues.append("Leading: it suggests the answer you want. Ask what happened instead.")
    if _HYPOTHETICAL.search(q):
        issues.append(
            "Hypothetical: people are poor predictors of their own behaviour. "
            "Ask about the last time it actually happened."
        )
    if _PITCH.search(q):
        issues.append("Pitches a solution: keep your idea out of discovery questions.")
    if _CLOSED_START.match(q) and not _OPEN_AFTER_CLOSED.match(q):
        issues.append("Closed: it invites a yes/no answer. Start with what, how or tell me.")
    if _LOADED.search(q):
        issues.append("Loaded wording: emotional words prime the answer. Use neutral terms.")
    if q.count("?") > 1 or re.search(r"\?\s*(and|or)\b", q, re.IGNORECASE):
        issues.append("Double-barrelled: ask one thing at a time.")
    if len(q.split()) > MAX_WORDS:
        issues.append(f"Long ({len(q.split())} words): shorter questions get clearer answers.")
    return issues
