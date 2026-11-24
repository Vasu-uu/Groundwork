"""The human checkpoint: founder review of every AI-suggested verdict.

- Each verdict is an "AI suggestion" until the founder approves it, changes
  it (with a reason), or rejects it (with a reason). Quotes can be removed and
  notes added. Every save is written to the append-only decision log with a
  before/after snapshot and a timestamp.
- `approve_study` refuses until every hypothesis has a review; with fewer than
  5 interviews it also needs an explicit acknowledgement that the evidence is
  provisional.
- `require_approved` is the server-side gate every downstream step (next
  interview script, export) must call. The UI disabling a button is a
  convenience; this function is the enforcement.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import ReviewRow, StudyRow, utcnow
from app.models.analysis import HypothesisVerdict, InterviewAssessment, VerdictLabel
from app.services.assessment import final_stance
from app.services.errors import CheckpointError, ConflictError, InvalidInputError, NotFoundError
from app.services.studies import (
    Actor,
    StudyStatus,
    corpus_of,
    log_event,
    result_of,
    reviews_of,
)
from app.services.verdicts import build_verdict

MIN_REASON_CHARS = 5


class Decision(StrEnum):
    APPROVE = "approve"  # accept the AI suggestion as the founder's decision
    CHANGE = "change"  # replace it with a different verdict (reason required)
    REJECT = "reject"  # discard it: the evidence is not trusted, re-test (reason required)


class ReviewInput(BaseModel):
    decision: Decision
    verdict: VerdictLabel | None = Field(
        default=None, description="Required for 'change': the founder's verdict"
    )
    reasoning: str = Field(default="", max_length=2000)
    removed_evidence: list[str] = Field(default_factory=list, max_length=200)
    note: str = Field(default="", max_length=2000)


class CheckpointState(BaseModel):
    total: int
    reviewed: int
    missing: list[str]
    approved: bool
    can_approve: bool
    needs_small_sample_ack: bool


# --- Helpers -------------------------------------------------------------------------------


def _verdict(row: StudyRow, hypothesis_id: str) -> HypothesisVerdict:
    result = result_of(row)
    if result is None:
        raise ConflictError("Run the analysis before reviewing.", code="no_analysis")
    for v in result.verdicts:
        if v.hypothesis.id == hypothesis_id:
            return v
    raise NotFoundError(f"Hypothesis {hypothesis_id} not found in this analysis.")


def recompute_without(
    verdict: HypothesisVerdict, removed: set[str], *, small_sample: bool
) -> VerdictLabel:
    """The verdict the rules would give if the removed quotes were never there."""
    if not removed:
        return verdict.verdict
    trimmed: list[InterviewAssessment] = []
    for a in verdict.assessments:
        sup = [e for e in a.supporting if e.key not in removed]
        con = [e for e in a.contradicting if e.key not in removed]
        stance = final_stance([a.stance], bool(sup), bool(con))
        trimmed.append(
            a.model_copy(update={"supporting": sup, "contradicting": con, "stance": stance})
        )
    return build_verdict(verdict.hypothesis, trimmed, small_sample=small_sample).verdict


def review_snapshot(r: ReviewRow | None) -> dict | None:
    if r is None:
        return None
    return {
        "decision": r.decision,
        "final_verdict": r.final_verdict,
        "reasoning": r.reasoning,
        "removed_evidence": list(r.removed_evidence),
        "note": r.note,
    }


# --- Commands ------------------------------------------------------------------------------


def save_review(db: Session, row: StudyRow, hypothesis_id: str, data: ReviewInput) -> ReviewRow:
    status = StudyStatus(row.status)
    if status is StudyStatus.APPROVED:
        raise ConflictError(
            "This study is approved and locked. Reopen the review to change decisions.",
            code="locked",
        )
    if status is not StudyStatus.AWAITING_REVIEW:
        raise ConflictError("There is no analysis waiting for review.", code="no_analysis")

    verdict = _verdict(row, hypothesis_id)
    valid_keys = {e.key for e in verdict.supporting + verdict.contradicting}
    unknown = set(data.removed_evidence) - valid_keys
    if unknown:
        raise InvalidInputError(f"Unknown quote reference(s): {', '.join(sorted(unknown))}.")

    reasoning = data.reasoning.strip()
    if data.decision is Decision.CHANGE:
        if data.verdict is None:
            raise InvalidInputError("Choose the verdict you want instead of the AI suggestion.")
        if data.verdict is verdict.verdict:
            raise InvalidInputError("That is the AI's verdict already; use approve instead.")
    if data.decision in (Decision.CHANGE, Decision.REJECT) and len(reasoning) < MIN_REASON_CHARS:
        raise InvalidInputError(
            "Explain your decision in a few words; it goes in the decision log."
        )

    final = {
        Decision.APPROVE: verdict.verdict,
        Decision.CHANGE: data.verdict,
        Decision.REJECT: None,
    }[data.decision]

    existing = reviews_of(db, row.id).get(hypothesis_id)
    before = review_snapshot(existing)
    review = existing or ReviewRow(study_id=row.id, hypothesis_id=hypothesis_id)
    review.decision = data.decision.value
    review.ai_verdict = verdict.verdict.value
    review.final_verdict = final.value if final else None
    review.reasoning = reasoning
    review.removed_evidence = sorted(set(data.removed_evidence))
    review.note = data.note.strip()
    review.reviewed_at = utcnow()
    if existing is None:
        db.add(review)

    log_event(
        db,
        row.id,
        Actor.FOUNDER,
        "review_saved",
        hypothesis_id=hypothesis_id,
        ai_suggestion=verdict.verdict.value,
        before=before,
        after=review_snapshot(review),
    )
    row.updated_at = utcnow()
    return review


def checkpoint_state(db: Session, row: StudyRow) -> CheckpointState:
    result = result_of(row)
    ids = [v.hypothesis.id for v in result.verdicts] if result else []
    reviewed = reviews_of(db, row.id)
    missing = [h for h in ids if h not in reviewed]
    status = StudyStatus(row.status)
    return CheckpointState(
        total=len(ids),
        reviewed=len(ids) - len(missing),
        missing=missing,
        approved=status is StudyStatus.APPROVED,
        can_approve=status is StudyStatus.AWAITING_REVIEW and bool(ids) and not missing,
        needs_small_sample_ack=corpus_of(row).small_sample,
    )


def approve_study(db: Session, row: StudyRow, *, acknowledge_small_sample: bool = False) -> None:
    state = checkpoint_state(db, row)
    if state.approved:
        raise ConflictError("This study is already approved.", code="already_approved")
    if StudyStatus(row.status) is not StudyStatus.AWAITING_REVIEW:
        raise ConflictError("There is no analysis waiting for review.", code="no_analysis")
    if state.missing:
        raise CheckpointError(
            f"Review every verdict before approving. Still to review: {', '.join(state.missing)}."
        )
    if state.needs_small_sample_ack and not acknowledge_small_sample:
        raise CheckpointError(
            "This study has fewer than 5 interviews. Confirm that you understand these "
            "verdicts are provisional before approving.",
            code="small_sample_ack_required",
        )
    reviews = reviews_of(db, row.id)
    row.status = StudyStatus.APPROVED.value
    row.approved_at = utcnow()
    row.updated_at = row.approved_at
    log_event(
        db,
        row.id,
        Actor.FOUNDER,
        "approved",
        acknowledged_small_sample=acknowledge_small_sample,
        decisions={h: r.decision for h, r in reviews.items()},
        final_verdicts={h: r.final_verdict for h, r in reviews.items()},
    )


def reopen_study(db: Session, row: StudyRow, reason: str = "") -> None:
    if StudyStatus(row.status) is not StudyStatus.APPROVED:
        raise ConflictError("Only an approved study can be reopened.", code="not_approved")
    row.status = StudyStatus.AWAITING_REVIEW.value
    row.approved_at = None
    row.updated_at = utcnow()
    log_event(db, row.id, Actor.FOUNDER, "reopened", reason=reason.strip())


def require_approved(row: StudyRow) -> None:
    """Server-side gate for every step after the human checkpoint."""
    if StudyStatus(row.status) is not StudyStatus.APPROVED:
        raise CheckpointError(
            "Human checkpoint: review and approve every verdict before this step can run."
        )
