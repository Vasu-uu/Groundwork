"""Studies API: inputs, analysis, the human checkpoint, and the decision log.

Write endpoints commit before returning, so a client (or the background
analysis) never reads stale state right after a response.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_db, get_provider, get_runner
from app.api.schemas import (
    ApproveIn,
    CreateStudyIn,
    FileError,
    FinalDecisionOut,
    HypothesesIn,
    InterviewSummary,
    LogEntryOut,
    PasteIn,
    ReopenIn,
    ReviewOut,
    ScriptEditIn,
    StatusOut,
    StudyOut,
    StudySummaryOut,
    UploadOut,
)
from app.config import Settings
from app.db.models import StudyRow
from app.llm import LLMProvider, UsageTracker, default_options
from app.models.script import InterviewScript
from app.models.transcript import Transcript
from app.services import report as report_svc
from app.services import review as review_svc
from app.services import script as script_svc
from app.services import studies as svc
from app.services.analysis import validate_inputs
from app.services.corpus import parse_upload
from app.services.documents import MAX_FILE_BYTES, DocumentError
from app.services.errors import InvalidInputError, NotFoundError
from app.services.runner import AnalysisRunner
from app.services.samples import SampleSetInfo, list_sample_sets, load_sample_set
from app.services.segmentation import segment_transcript

router = APIRouter(tags=["studies"])

DB = Annotated[Session, Depends(get_db)]
Runner = Annotated[AnalysisRunner, Depends(get_runner)]
Provider = Annotated[LLMProvider, Depends(get_provider)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]


# --- Helpers -------------------------------------------------------------------------------


def _study_out(db: Session, row: StudyRow, runner: AnalysisRunner) -> StudyOut:
    corpus = svc.corpus_of(row)
    result = svc.result_of(row)
    verdicts = {v.hypothesis.id: v for v in result.verdicts} if result else {}
    reviews = {}
    for hid, r in svc.reviews_of(db, row.id).items():
        verdict = verdicts.get(hid)
        recomputed = (
            review_svc.recompute_without(
                verdict, set(r.removed_evidence), small_sample=corpus.small_sample
            )
            if verdict
            else r.ai_verdict
        )
        reviews[hid] = ReviewOut(
            hypothesis_id=hid,
            decision=r.decision,
            ai_verdict=r.ai_verdict,
            final_verdict=r.final_verdict,
            reasoning=r.reasoning,
            removed_evidence=list(r.removed_evidence),
            note=r.note,
            reviewed_at=r.reviewed_at,
            recomputed_ai_verdict=recomputed,
        )
    return StudyOut(
        id=row.id,
        name=row.name,
        status=row.status,
        progress=row.progress,
        error=row.error,
        error_kind=row.error_kind,
        sample_set=row.sample_set,
        created_at=row.created_at,
        updated_at=row.updated_at,
        analyzed_at=row.analyzed_at,
        approved_at=row.approved_at,
        hypotheses=svc.hypotheses_of(row),
        interviews=[InterviewSummary.of(t) for t in corpus.transcripts],
        corpus_warnings=corpus.warnings,
        small_sample=corpus.small_sample,
        result=result,
        reviews=reviews,
        checkpoint=review_svc.checkpoint_state(db, row),
        usage=runner.live_usage(row.id) or svc.usage_of(db, row.id),
    )


# --- Samples (demo data) ----------------------------------------------------------------------


@router.get("/samples", response_model=list[SampleSetInfo])
def samples() -> list[SampleSetInfo]:
    return list_sample_sets()


@router.post("/studies/from-sample/{set_id}", response_model=StudyOut, status_code=201)
def create_from_sample(set_id: str, db: DB, runner: Runner) -> StudyOut:
    try:
        sample = load_sample_set(set_id)
    except KeyError as exc:
        raise NotFoundError(f"Unknown sample set: {set_id}") from exc
    row = svc.create_study(
        db, sample.name, sample.hypotheses, sample.corpus.transcripts, sample_set=set_id
    )
    db.commit()
    return _study_out(db, row, runner)


# --- Studies and inputs ------------------------------------------------------------------------


@router.get("/studies", response_model=list[StudySummaryOut])
def list_all(db: DB) -> list[StudySummaryOut]:
    return [
        StudySummaryOut(
            id=r.id,
            name=r.name,
            status=r.status,
            sample_set=r.sample_set,
            created_at=r.created_at,
            interviews=len(r.transcripts),
            hypotheses=len(r.hypotheses),
        )
        for r in svc.list_studies(db)
    ]


@router.post("/studies", response_model=StudyOut, status_code=201)
def create(body: CreateStudyIn, db: DB, runner: Runner) -> StudyOut:
    row = svc.create_study(db, body.name, svc.normalize_hypotheses(body.hypotheses))
    db.commit()
    return _study_out(db, row, runner)


@router.get("/studies/{study_id}", response_model=StudyOut)
def get(study_id: str, db: DB, runner: Runner) -> StudyOut:
    return _study_out(db, svc.get_study(db, study_id), runner)


@router.put("/studies/{study_id}/hypotheses", response_model=StudyOut)
def put_hypotheses(study_id: str, body: HypothesesIn, db: DB, runner: Runner) -> StudyOut:
    row = svc.get_study(db, study_id)
    svc.set_hypotheses(db, row, svc.normalize_hypotheses(body.hypotheses))
    db.commit()
    return _study_out(db, row, runner)


@router.post("/studies/{study_id}/interviews", response_model=UploadOut)
async def upload(study_id: str, db: DB, files: Annotated[list[UploadFile], File()]) -> UploadOut:
    """Upload .txt, .md, .pdf or .docx files. Bad files are reported, good ones kept."""
    row = svc.get_study(db, study_id)
    parsed: list[Transcript] = []
    errors: list[FileError] = []
    for f in files:
        name = f.filename or "upload.txt"
        data = await f.read(MAX_FILE_BYTES + 1)
        try:
            parsed.append(parse_upload(name, data))
        except DocumentError as exc:
            errors.append(FileError(filename=name, error=str(exc)))
    added = svc.add_transcripts(db, row, parsed) if parsed else []
    db.commit()
    return UploadOut(added=[InterviewSummary.of(t) for t in added], errors=errors)


@router.post("/studies/{study_id}/interviews/text", response_model=UploadOut)
def paste(study_id: str, body: PasteIn, db: DB) -> UploadOut:
    """Add an interview pasted as text."""
    row = svc.get_study(db, study_id)
    title = body.title.strip() or "pasted interview"
    transcript = segment_transcript(body.text, source_filename=f"{title}.txt")
    if not transcript.segments:
        raise InvalidInputError("The pasted text is empty.")
    added = svc.add_transcripts(db, row, [transcript])
    db.commit()
    return UploadOut(added=[InterviewSummary.of(t) for t in added], errors=[])


@router.get("/studies/{study_id}/interviews/{interview_id}", response_model=Transcript)
def transcript(study_id: str, interview_id: str, db: DB) -> Transcript:
    """Full transcript with segments and offsets, for the source panel."""
    return svc.get_transcript(svc.get_study(db, study_id), interview_id)


@router.delete("/studies/{study_id}/interviews/{interview_id}", status_code=204)
def remove_interview(study_id: str, interview_id: str, db: DB) -> None:
    svc.remove_transcript(db, svc.get_study(db, study_id), interview_id)
    db.commit()


# --- Analysis -------------------------------------------------------------------------------------


@router.post("/studies/{study_id}/analyze", response_model=StatusOut, status_code=202)
def analyze(study_id: str, db: DB, runner: Runner, background: BackgroundTasks) -> StatusOut:
    """Start the analysis in the background; poll `/status` for progress."""
    row = svc.get_study(db, study_id)
    validate_inputs(svc.corpus_of(row), svc.hypotheses_of(row))
    svc.mark_analyzing(db, row)
    db.commit()
    background.add_task(runner.run, study_id)
    return status(study_id, db, runner)


@router.get("/studies/{study_id}/status", response_model=StatusOut)
def status(study_id: str, db: DB, runner: Runner) -> StatusOut:
    row = svc.get_study(db, study_id)
    return StatusOut(
        status=row.status,
        progress=row.progress,
        error=row.error,
        error_kind=row.error_kind,
        usage=runner.live_usage(study_id) or svc.usage_of(db, study_id),
    )


# --- Human checkpoint ----------------------------------------------------------------------------


@router.put("/studies/{study_id}/reviews/{hypothesis_id}", response_model=StudyOut)
def put_review(
    study_id: str, hypothesis_id: str, body: review_svc.ReviewInput, db: DB, runner: Runner
) -> StudyOut:
    """Approve, change or reject one AI-suggested verdict (logged with a timestamp)."""
    row = svc.get_study(db, study_id)
    review_svc.save_review(db, row, hypothesis_id, body)
    db.commit()
    return _study_out(db, row, runner)


@router.post("/studies/{study_id}/approve", response_model=StudyOut)
def approve(study_id: str, body: ApproveIn, db: DB, runner: Runner) -> StudyOut:
    """Pass the human checkpoint. Refused until every verdict has been reviewed."""
    row = svc.get_study(db, study_id)
    review_svc.approve_study(db, row, acknowledge_small_sample=body.acknowledge_small_sample)
    db.commit()
    return _study_out(db, row, runner)


@router.post("/studies/{study_id}/reopen", response_model=StudyOut)
def reopen(study_id: str, body: ReopenIn, db: DB, runner: Runner) -> StudyOut:
    row = svc.get_study(db, study_id)
    review_svc.reopen_study(db, row, body.reason)
    db.commit()
    return _study_out(db, row, runner)


@router.get("/studies/{study_id}/decisions", response_model=list[FinalDecisionOut])
def final_decisions(study_id: str, db: DB) -> list[FinalDecisionOut]:
    """The founder's approved decisions. Gated: 409 until the checkpoint is passed."""
    return review_svc.final_decisions(db, svc.get_study(db, study_id))


@router.get("/studies/{study_id}/decision-log", response_model=list[LogEntryOut])
def get_log(study_id: str, db: DB) -> list[LogEntryOut]:
    svc.get_study(db, study_id)
    return [
        LogEntryOut(
            id=e.id,
            at=e.at,
            actor=e.actor,
            action=e.action,
            hypothesis_id=e.hypothesis_id,
            details=e.details,
        )
        for e in svc.decision_log(db, study_id)
    ]


# --- After the checkpoint: next interview script and export -------------------------------------


@router.post("/studies/{study_id}/script", response_model=InterviewScript)
async def generate_script(
    study_id: str, db: DB, provider: Provider, settings: AppSettings
) -> InterviewScript:
    """Draft the next interview script from the approved decisions (replaces any previous one).

    Gated by the human checkpoint. Runs one model call synchronously.
    """
    row = svc.get_study(db, study_id)
    tracker = UsageTracker(f"script-{uuid.uuid4().hex[:8]}")
    try:
        script = await script_svc.generate_for_study(
            db,
            row,
            provider,
            options=default_options(settings),
            tracker=tracker,
            max_retries=settings.llm_max_retries,
        )
    finally:
        # Count the tokens even when the provider failed part-way.
        if tracker.records:
            svc.save_calls(db, study_id, tracker.run_id, tracker.records)
            db.commit()
    script_svc.save_script(db, row, script, action="script_generated")
    db.commit()
    return script


@router.get("/studies/{study_id}/script", response_model=InterviewScript)
def get_script(study_id: str, db: DB) -> InterviewScript:
    return script_svc.require_script(db, svc.get_study(db, study_id))


@router.put("/studies/{study_id}/script", response_model=InterviewScript)
def edit_script(study_id: str, body: ScriptEditIn, db: DB) -> InterviewScript:
    """Save the founder's edits. Edited questions are linted again."""
    row = svc.get_study(db, study_id)
    script = script_svc.apply_edits(script_svc.require_script(db, row), body.questions)
    script_svc.save_script(db, row, script, action="script_edited")
    db.commit()
    return script


def _filename(row: StudyRow, ext: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in row.name.lower()).strip("-")
    return f"groundwork-{'-'.join(filter(None, slug.split('-')))[:60] or row.id}.{ext}"


@router.get("/studies/{study_id}/report.md", response_class=Response)
def report_markdown(study_id: str, db: DB) -> Response:
    """The approved study as Markdown: decisions, evidence, themes, script, log, AI usage."""
    row = svc.get_study(db, study_id)
    text = report_svc.to_markdown(report_svc.report_for_study(db, row))
    return Response(
        text,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_filename(row, "md")}"'},
    )


@router.get("/studies/{study_id}/report.pdf", response_class=Response)
def report_pdf(study_id: str, db: DB) -> Response:
    """The same report as a PDF."""
    row = svc.get_study(db, study_id)
    pdf = report_svc.to_pdf(report_svc.report_for_study(db, row))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_filename(row, "pdf")}"'},
    )
