"""Studies: persistence, the status state machine, and the decision log.

Status transitions (anything else raises `ConflictError`):

    draft ----analyze----> analyzing --ok--> awaiting_review --approve--> approved
      ^                        |                    |  ^                     |
      |                        +--error--> failed   |  +------reopen---------+
      +---- inputs changed (clears result and reviews) ----+

Approved studies are locked: interviews, hypotheses and reviews cannot change
until the founder explicitly reopens the review.
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import DecisionLogRow, LLMCallRow, ReviewRow, StudyRow, utcnow
from app.llm.usage import CallRecord, UsageSummary
from app.models.analysis import AnalysisResult
from app.models.hypothesis import Hypothesis
from app.models.transcript import Transcript
from app.services.corpus import Corpus, build_corpus
from app.services.errors import ConflictError, InvalidInputError, NotFoundError

MAX_INTERVIEWS = 50


class StudyStatus(StrEnum):
    DRAFT = "draft"
    ANALYZING = "analyzing"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    FAILED = "failed"


EDITABLE = {StudyStatus.DRAFT, StudyStatus.FAILED, StudyStatus.AWAITING_REVIEW}


class Actor(StrEnum):
    FOUNDER = "founder"
    AI = "ai"
    SYSTEM = "system"


# --- Basic access ---------------------------------------------------------------------


def log_event(
    db: Session,
    study_id: str,
    actor: Actor,
    action: str,
    *,
    hypothesis_id: str | None = None,
    **details: Any,
) -> None:
    db.add(
        DecisionLogRow(
            study_id=study_id,
            actor=actor.value,
            action=action,
            hypothesis_id=hypothesis_id,
            details=details,
        )
    )


def get_study(db: Session, study_id: str) -> StudyRow:
    row = db.get(StudyRow, study_id)
    if row is None:
        raise NotFoundError(f"Study {study_id} not found.")
    return row


def list_studies(db: Session) -> list[StudyRow]:
    return list(db.scalars(select(StudyRow).order_by(StudyRow.created_at.desc())))


def hypotheses_of(row: StudyRow) -> list[Hypothesis]:
    return [Hypothesis.model_validate(h) for h in row.hypotheses]


def corpus_of(row: StudyRow) -> Corpus:
    return build_corpus([Transcript.model_validate(t) for t in row.transcripts])


def result_of(row: StudyRow) -> AnalysisResult | None:
    return AnalysisResult.model_validate(row.result) if row.result else None


def reviews_of(db: Session, study_id: str) -> dict[str, ReviewRow]:
    rows = db.scalars(select(ReviewRow).where(ReviewRow.study_id == study_id))
    return {r.hypothesis_id: r for r in rows}


def decision_log(db: Session, study_id: str) -> list[DecisionLogRow]:
    return list(
        db.scalars(
            select(DecisionLogRow)
            .where(DecisionLogRow.study_id == study_id)
            .order_by(DecisionLogRow.id)
        )
    )


def usage_of(db: Session, study_id: str) -> UsageSummary:
    rows = list(db.scalars(select(LLMCallRow).where(LLMCallRow.study_id == study_id)))
    prompt = sum(r.prompt_tokens for r in rows)
    completion = sum(r.completion_tokens for r in rows)
    return UsageSummary(
        run_id=study_id,
        calls=len(rows),
        failed_calls=sum(1 for r in rows if not r.ok),
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        providers=sorted({r.provider for r in rows}),
        models=sorted({r.model for r in rows}),
    )


def _status(row: StudyRow) -> StudyStatus:
    return StudyStatus(row.status)


def _touch(row: StudyRow) -> None:
    row.updated_at = utcnow()


# --- Inputs -------------------------------------------------------------------------------


def normalize_hypotheses(texts: list[str]) -> list[Hypothesis]:
    """Clean founder-entered hypothesis texts and number them H1..Hn."""
    cleaned = [" ".join(t.split()) for t in texts]
    cleaned = [t for t in cleaned if t]
    if len({t.casefold() for t in cleaned}) != len(cleaned):
        raise InvalidInputError("Each hypothesis must be different.")
    try:
        return [Hypothesis(id=f"H{i}", text=t) for i, t in enumerate(cleaned, start=1)]
    except ValueError as exc:
        raise InvalidInputError("Each hypothesis must be 3 to 500 characters long.") from exc


def create_study(
    db: Session,
    name: str,
    hypotheses: list[Hypothesis],
    transcripts: list[Transcript] | None = None,
    *,
    sample_set: str | None = None,
) -> StudyRow:
    name = " ".join(name.split())[:200] or "Untitled study"
    row = StudyRow(
        id=uuid.uuid4().hex[:12],
        name=name,
        status=StudyStatus.DRAFT.value,
        sample_set=sample_set,
        hypotheses=[h.model_dump() for h in hypotheses],
        transcripts=[t.model_dump(mode="json") for t in (transcripts or [])],
    )
    db.add(row)
    db.flush()
    log_event(
        db,
        row.id,
        Actor.FOUNDER,
        "study_created",
        name=name,
        sample_set=sample_set,
        hypotheses=[h.text for h in hypotheses],
        interviews=len(row.transcripts),
    )
    return row


def _reset_analysis(db: Session, row: StudyRow, reason: str) -> None:
    """Inputs changed: the old analysis and reviews no longer apply."""
    if row.result is None and _status(row) is StudyStatus.DRAFT:
        return
    db.execute(delete(ReviewRow).where(ReviewRow.study_id == row.id))
    row.result = None
    row.analyzed_at = None
    row.error = row.error_kind = row.progress = None
    row.status = StudyStatus.DRAFT.value
    log_event(db, row.id, Actor.SYSTEM, "analysis_reset", reason=reason)


def _require_editable(row: StudyRow) -> None:
    status = _status(row)
    if status is StudyStatus.APPROVED:
        raise ConflictError(
            "This study is approved and locked. Reopen the review to change it.", code="locked"
        )
    if status is StudyStatus.ANALYZING:
        raise ConflictError("Analysis is running; wait for it to finish.", code="busy")


def add_transcripts(db: Session, row: StudyRow, new: list[Transcript]) -> list[Transcript]:
    """Append interviews (IDs made unique). Returns the added transcripts as stored."""
    _require_editable(row)
    existing = [Transcript.model_validate(t) for t in row.transcripts]
    if len(existing) + len(new) > MAX_INTERVIEWS:
        raise InvalidInputError(f"A study can hold at most {MAX_INTERVIEWS} interviews.")
    corpus = build_corpus(existing + new)
    added = corpus.transcripts[len(existing) :]
    row.transcripts = [t.model_dump(mode="json") for t in corpus.transcripts]
    _reset_analysis(db, row, "interviews added")
    _touch(row)
    log_event(
        db,
        row.id,
        Actor.FOUNDER,
        "interviews_added",
        interviews=[{"id": t.id, "source": t.source_filename} for t in added],
    )
    return added


def remove_transcript(db: Session, row: StudyRow, interview_id: str) -> None:
    _require_editable(row)
    before = len(row.transcripts)
    row.transcripts = [t for t in row.transcripts if t["id"] != interview_id]
    if len(row.transcripts) == before:
        raise NotFoundError(f"Interview {interview_id} not found in this study.")
    _reset_analysis(db, row, f"interview {interview_id} removed")
    _touch(row)
    log_event(db, row.id, Actor.FOUNDER, "interview_removed", interview_id=interview_id)


def set_hypotheses(db: Session, row: StudyRow, hypotheses: list[Hypothesis]) -> None:
    _require_editable(row)
    old = [h["text"] for h in row.hypotheses]
    new = [h.text for h in hypotheses]
    if old == new:
        return
    row.hypotheses = [h.model_dump() for h in hypotheses]
    _reset_analysis(db, row, "hypotheses changed")
    _touch(row)
    log_event(db, row.id, Actor.FOUNDER, "hypotheses_updated", before=old, after=new)


def get_transcript(row: StudyRow, interview_id: str) -> Transcript:
    for t in row.transcripts:
        if t["id"] == interview_id:
            return Transcript.model_validate(t)
    raise NotFoundError(f"Interview {interview_id} not found in this study.")


# --- Analysis lifecycle -----------------------------------------------------------------


def mark_analyzing(db: Session, row: StudyRow) -> None:
    status = _status(row)
    if status is StudyStatus.ANALYZING:
        raise ConflictError("Analysis is already running.", code="busy")
    if status is StudyStatus.APPROVED:
        raise ConflictError(
            "This study is approved and locked. Reopen the review to re-run it.", code="locked"
        )
    if status is StudyStatus.AWAITING_REVIEW:
        db.execute(delete(ReviewRow).where(ReviewRow.study_id == row.id))
        log_event(db, row.id, Actor.SYSTEM, "reviews_cleared", reason="analysis re-run")
    row.status = StudyStatus.ANALYZING.value
    row.progress = "queued"
    row.error = row.error_kind = None
    _touch(row)
    log_event(db, row.id, Actor.FOUNDER, "analysis_started")


def set_progress(db: Session, row: StudyRow, step: str) -> None:
    row.progress = step
    _touch(row)


def save_calls(db: Session, study_id: str, run_id: str, records: list[CallRecord]) -> None:
    for r in records:
        db.add(
            LLMCallRow(
                study_id=study_id,
                run_id=run_id,
                purpose=r.purpose[:200],
                provider=r.provider,
                model=r.model,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                latency_ms=r.latency_ms,
                ok=r.ok,
                at=r.at,
            )
        )


def complete_analysis(db: Session, row: StudyRow, result: AnalysisResult) -> None:
    row.result = result.model_dump(mode="json")
    row.status = StudyStatus.AWAITING_REVIEW.value
    row.progress = None
    row.analyzed_at = utcnow()
    _touch(row)
    log_event(
        db,
        row.id,
        Actor.AI,
        "analysis_completed",
        run_id=result.run_id,
        pain_points=len(result.pain_points),
        themes=len(result.clustering.themes),
        verified_quotes=result.quote_stats.label(),
        suggestions={v.hypothesis.id: v.verdict.value for v in result.verdicts},
        prompts=result.prompt_ids,
        warnings=result.warnings,
    )


def fail_analysis(db: Session, row: StudyRow, kind: str, message: str) -> None:
    row.status = StudyStatus.FAILED.value
    row.progress = None
    row.error = message
    row.error_kind = kind
    _touch(row)
    log_event(db, row.id, Actor.SYSTEM, "analysis_failed", kind=kind, error=message)


def recover_interrupted(db: Session) -> int:
    """On startup: analyses that were running when the server stopped have failed."""
    rows = list(db.scalars(select(StudyRow).where(StudyRow.status == StudyStatus.ANALYZING)))
    for row in rows:
        fail_analysis(db, row, "interrupted", "The server stopped during analysis. Run it again.")
    return len(rows)
