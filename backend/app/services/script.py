"""Draft the next interview script from the founder's approved decisions.

Code decides WHAT to ask about; the model only drafts the wording:

1. Targets (code): every hypothesis the founder left uncertain (UNTESTED,
   MIXED, or rejected for re-testing) and the strongest pain themes. Settled
   hypotheses (VALIDATED/INVALIDATED by the founder) are not re-asked.
2. Wording (model, `draft_interview_script.v*`): one or two non-leading
   questions per target, each with a purpose and a bias check.
3. Checks (code): every question is linted for leading, hypothetical, closed
   or loaded wording. Targets the model skipped get a placeholder the founder
   must write, so nothing is silently dropped.
4. Fixed warm-up and wrap-up questions frame the interview.

Only approved studies can get a script (`require_approved`).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.db.models import ScriptRow, StudyRow, utcnow
from app.llm import GenerationOptions, LLMProvider, UsageTracker
from app.llm.prompts import PromptTemplate, load_prompt
from app.llm.structured import StructuredOutputError, generate_structured
from app.models.analysis import AnalysisResult, VerdictLabel
from app.models.script import (
    InterviewScript,
    ScriptQuestion,
    ScriptTarget,
    Section,
    TargetKind,
)
from app.services.errors import InvalidInputError, NotFoundError
from app.services.question_lint import lint_question
from app.services.review import FinalDecision, final_decisions, require_approved
from app.services.studies import Actor, log_event, result_of

logger = logging.getLogger("groundwork.script")

PROMPT_NAME = "draft_interview_script"
MAX_THEMES = 3
MAX_QUESTIONS_PER_TARGET = 2
MAX_QUESTIONS = 40

WARMUP = [
    ScriptQuestion(
        id="W1",
        section=Section.WARMUP,
        question="To start, can you walk me through your role and what a typical week looks like?",
        purpose="Context about the person before any topic is introduced.",
        bias_check="Open and topic-free, so nothing you care about is signalled yet.",
    ),
]
WRAPUP = [
    ScriptQuestion(
        id="X1",
        section=Section.WRAPUP,
        question="Is there anything about how you handle this that we haven't covered?",
        purpose="Surface problems you did not think to ask about.",
        bias_check="Lets the customer set the agenda instead of confirming yours.",
    ),
    ScriptQuestion(
        id="X2",
        section=Section.WRAPUP,
        question="Who else should I talk to about this?",
        purpose="Find the next interviewee through the customer's own network.",
        bias_check="Neutral request; no opinion is asked for.",
    ),
]


# --- Targets ----------------------------------------------------------------------------------


def _decision_label(d: FinalDecision) -> str:
    if d.final_verdict is None:
        return "rejected by the founder: re-test"
    return d.final_verdict.value


def select_targets(decisions: list[FinalDecision], result: AnalysisResult) -> list[ScriptTarget]:
    """What the next interview must learn about, with the reason for each."""
    targets: list[ScriptTarget] = []
    for d in decisions:
        open_question = d.final_verdict in (None, VerdictLabel.UNTESTED, VerdictLabel.MIXED)
        if not open_question:
            continue
        if d.final_verdict is None:
            reason = "You rejected the evidence for this verdict; it needs a clean re-test."
        elif d.final_verdict is VerdictLabel.MIXED:
            reason = (
                f"Evidence is split ({len(d.supporting)} supporting, "
                f"{len(d.contradicting)} contradicting quotes); find out what separates the two."
            )
        else:
            reason = "Not enough interviewees discussed it to judge."
        if d.reasoning:
            reason += f" Your note: “{d.reasoning}”"
        targets.append(
            ScriptTarget(id=d.hypothesis_id, kind=TargetKind.HYPOTHESIS, text=d.text, reason=reason)
        )
    themes = sorted(result.clustering.themes, key=lambda t: (-t.frequency, t.id))[:MAX_THEMES]
    for t in themes:
        targets.append(
            ScriptTarget(
                id=t.id,
                kind=TargetKind.THEME,
                text=t.label,
                reason=(
                    f"Mentioned by {t.frequency} of {result.interview_count} interviewees; "
                    "learn how often it happens, what it costs, and what they do about it today."
                ),
            )
        )
    return targets


def _render_hypothesis_targets(targets: list[ScriptTarget], decisions: list[FinalDecision]) -> str:
    by_id = {d.hypothesis_id: d for d in decisions}
    lines = []
    for t in targets:
        if t.kind is not TargetKind.HYPOTHESIS:
            continue
        d = by_id[t.id]
        line = f"- {t.id} [{_decision_label(d)}]: {t.text}"
        if d.reasoning:
            line += f"\n  Founder's reasoning: {d.reasoning}"
        lines.append(line)
    return "\n".join(lines) or "(none: every hypothesis has a firm decision)"


def _render_theme_targets(targets: list[ScriptTarget], result: AnalysisResult) -> str:
    points = {p.id: p for p in result.pain_points}
    themes = {t.id: t for t in result.clustering.themes}
    lines = []
    for t in targets:
        if t.kind is not TargetKind.THEME:
            continue
        theme = themes[t.id]
        example = next((points[i].evidence.quote for i in theme.pain_point_ids if i in points), "")
        line = f"- {t.id} ({theme.frequency}/{result.interview_count} interviewees): {t.text}"
        if example:
            line += f'\n  Example quote: "{" ".join(example.split())[:200]}"'
        lines.append(line)
    return "\n".join(lines) or "(none)"


# --- Model output -----------------------------------------------------------------------------


class LLMQuestion(BaseModel):
    target: str
    question: str = Field(min_length=3, max_length=400)
    purpose: str = Field(default="", max_length=300)
    bias_check: str = Field(default="", max_length=400)
    follow_ups: list[str] = Field(default_factory=list)

    @field_validator("follow_ups", mode="before")
    @classmethod
    def _follow_ups(cls, v: Any) -> Any:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v


class ScriptOutput(BaseModel):
    questions: list[LLMQuestion] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _bare(cls, data: Any) -> Any:
        return {"questions": data} if isinstance(data, list) else data


def _clean(text: str) -> str:
    return " ".join(text.split()).strip().strip('"').strip()


def _placeholder(target: ScriptTarget, n: int) -> ScriptQuestion:
    what = "hypothesis" if target.kind is TargetKind.HYPOTHESIS else "pain theme"
    return ScriptQuestion(
        id=f"Q{n}",
        section=Section.HYPOTHESIS if target.kind is TargetKind.HYPOTHESIS else Section.PAIN,
        target=target.id,
        question="",
        purpose=f"Test the {what}: {target.text}",
        bias_check="",
        lint=["Write this question yourself: the model did not draft one for this target."],
        needs_edit=True,
    )


def assemble(
    targets: list[ScriptTarget], drafted: list[LLMQuestion]
) -> tuple[list[ScriptQuestion], list[str]]:
    """Order, number and lint the drafted questions; fill gaps with placeholders."""
    by_target: dict[str, list[LLMQuestion]] = {}
    known = {t.id.casefold(): t.id for t in targets}
    warnings: list[str] = []
    unknown = 0
    for q in drafted:
        tid = known.get(re.sub(r"[^\w-]", "", q.target).casefold())
        if tid is None:
            unknown += 1
            continue
        bucket = by_target.setdefault(tid, [])
        if len(bucket) < MAX_QUESTIONS_PER_TARGET and _clean(q.question):
            bucket.append(q)
    if unknown:
        warnings.append(
            f"Ignored {unknown} drafted question(s) for targets that were not asked for."
        )

    # Pain themes first (let the customer talk about their world), then hypotheses.
    order = [t for t in targets if t.kind is TargetKind.THEME] + [
        t for t in targets if t.kind is TargetKind.HYPOTHESIS
    ]
    questions: list[ScriptQuestion] = []
    n = 0
    for t in order:
        section = Section.PAIN if t.kind is TargetKind.THEME else Section.HYPOTHESIS
        drafted_for = by_target.get(t.id, [])
        if not drafted_for:
            n += 1
            questions.append(_placeholder(t, n))
            warnings.append(f"No question was drafted for {t.id}; write one yourself.")
            continue
        for q in drafted_for:
            n += 1
            text = _clean(q.question)
            questions.append(
                ScriptQuestion(
                    id=f"Q{n}",
                    section=section,
                    target=t.id,
                    question=text,
                    purpose=_clean(q.purpose),
                    bias_check=_clean(q.bias_check),
                    follow_ups=[f for f in (_clean(x) for x in q.follow_ups) if f][:2],
                    lint=lint_question(text),
                )
            )
    flagged = sum(1 for q in questions if q.lint and not q.needs_edit)
    if flagged:
        warnings.append(
            f"{flagged} drafted question(s) have wording problems flagged below. "
            "Fix them before the interview."
        )
    return questions, warnings


# --- Generation and storage -------------------------------------------------------------------


async def draft_script(
    study_name: str,
    decisions: list[FinalDecision],
    result: AnalysisResult,
    provider: LLMProvider,
    *,
    options: GenerationOptions | None = None,
    tracker: UsageTracker | None = None,
    max_retries: int = 2,
    prompt: PromptTemplate | None = None,
) -> InterviewScript:
    """Build the script.

    Provider errors propagate; unusable model output degrades to placeholders.
    """
    prompt = prompt or load_prompt(PROMPT_NAME)
    targets = select_targets(decisions, result)
    warnings: list[str] = []
    drafted: list[LLMQuestion] = []
    if targets:
        try:
            out = await generate_structured(
                provider,
                prompt.render(
                    study_name=study_name,
                    hypothesis_targets=_render_hypothesis_targets(targets, decisions),
                    theme_targets=_render_theme_targets(targets, result),
                ),
                ScriptOutput,
                options=options,
                tracker=tracker,
                purpose=f"{prompt.id}:{','.join(t.id for t in targets)}",
                max_retries=max_retries,
            )
            drafted = out.questions
        except StructuredOutputError as exc:
            logger.warning("script drafting failed: %s", exc)
            warnings.append(
                "The model's draft was unusable, so every targeted question is a placeholder "
                "for you to write. Try generating again, or write them yourself."
            )
    else:
        warnings.append(
            "Nothing left to target: no hypothesis is open and no pain theme was found."
        )

    questions, assemble_warnings = assemble(targets, drafted)
    return InterviewScript(
        generated_at=utcnow(),
        prompt_id=prompt.id if targets else None,
        model=f"{provider.name}:{provider.model}" if targets else None,
        targets=targets,
        questions=[q.model_copy() for q in WARMUP] + questions + [q.model_copy() for q in WRAPUP],
        warnings=warnings + assemble_warnings,
    )


def get_script(db: Session, row: StudyRow) -> InterviewScript | None:
    script_row = db.get(ScriptRow, row.id)
    return InterviewScript.model_validate(script_row.data) if script_row else None


def require_script(db: Session, row: StudyRow) -> InterviewScript:
    require_approved(row)
    script = get_script(db, row)
    if script is None:
        raise NotFoundError("No interview script yet. Generate one first.", code="no_script")
    return script


def save_script(db: Session, row: StudyRow, script: InterviewScript, *, action: str) -> None:
    script_row = db.get(ScriptRow, row.id)
    data = script.model_dump(mode="json")
    if script_row is None:
        db.add(ScriptRow(study_id=row.id, data=data))
    else:
        script_row.data = data
        script_row.updated_at = utcnow()
    actor = Actor.AI if action == "script_generated" else Actor.FOUNDER
    log_event(
        db,
        row.id,
        actor,
        action,
        questions=len(script.questions),
        targets=[t.id for t in script.targets],
        flagged=script.lint_count,
        prompt=script.prompt_id,
    )


async def generate_for_study(
    db: Session,
    row: StudyRow,
    provider: LLMProvider,
    *,
    options: GenerationOptions | None = None,
    tracker: UsageTracker | None = None,
    max_retries: int = 2,
) -> InterviewScript:
    decisions = final_decisions(db, row)  # enforces the checkpoint
    result = result_of(row)
    assert result is not None
    return await draft_script(
        row.name,
        decisions,
        result,
        provider,
        options=options,
        tracker=tracker,
        max_retries=max_retries,
    )


# --- Founder edits ----------------------------------------------------------------------------


class QuestionEdit(BaseModel):
    id: str | None = Field(default=None, description="Existing question ID; None for a new one")
    question: str = Field(max_length=400)
    follow_ups: list[str] = Field(default_factory=list, max_length=5)
    purpose: str = Field(default="", max_length=300)


def apply_edits(script: InterviewScript, edits: list[QuestionEdit]) -> InterviewScript:
    """Replace the question list with the founder's version (order, text, additions, removals).

    Questions keep their section, target and bias check; edited text is linted
    again, and the model's bias check is dropped when the wording changed
    (it described the old wording).
    """
    if len(edits) > MAX_QUESTIONS:
        raise InvalidInputError(f"A script can have at most {MAX_QUESTIONS} questions.")
    existing = {q.id: q for q in script.questions}
    used = set()
    out: list[ScriptQuestion] = []
    next_custom = 1 + sum(1 for q in script.questions if q.section is Section.CUSTOM)
    for e in edits:
        text = _clean(e.question)
        if not text:
            raise InvalidInputError("Questions cannot be empty; remove the question instead.")
        follow_ups = [f for f in (_clean(x) for x in e.follow_ups) if f]
        old = existing.get(e.id or "")
        if old is not None and old.id not in used:
            used.add(old.id)
            changed = text != old.question
            out.append(
                old.model_copy(
                    update={
                        "question": text,
                        "follow_ups": follow_ups,
                        "purpose": _clean(e.purpose) or old.purpose,
                        "bias_check": "" if changed else old.bias_check,
                        "lint": lint_question(text),
                        "needs_edit": False,
                        "edited": old.edited or changed or follow_ups != old.follow_ups,
                    }
                )
            )
        else:
            while f"C{next_custom}" in existing:
                next_custom += 1
            out.append(
                ScriptQuestion(
                    id=f"C{next_custom}",
                    section=Section.CUSTOM,
                    question=text,
                    purpose=_clean(e.purpose),
                    follow_ups=follow_ups,
                    lint=lint_question(text),
                    edited=True,
                )
            )
            next_custom += 1
    return script.model_copy(update={"questions": out, "edited_at": utcnow()})
