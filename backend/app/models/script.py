"""The next interview script: questions targeted at what is still uncertain."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Section(StrEnum):
    WARMUP = "warmup"  # context about the person, before any topic is introduced
    PAIN = "pain_followup"  # dig into the strongest pain themes
    HYPOTHESIS = "hypothesis"  # test hypotheses that are untested, mixed or rejected
    WRAPUP = "wrapup"
    CUSTOM = "custom"  # added by the founder


class TargetKind(StrEnum):
    HYPOTHESIS = "hypothesis"
    THEME = "theme"


class ScriptTarget(BaseModel):
    """Something the next interview should learn about, and why it was chosen."""

    id: str  # hypothesis ID (H2) or theme ID (T1)
    kind: TargetKind
    text: str
    reason: str


class ScriptQuestion(BaseModel):
    id: str
    section: Section
    target: str | None = None
    question: str
    purpose: str = ""
    bias_check: str = Field(
        default="", description="Which bias this wording risks and how it avoids it"
    )
    follow_ups: list[str] = Field(default_factory=list)
    lint: list[str] = Field(
        default_factory=list, description="Wording problems found by code, not by the model"
    )
    needs_edit: bool = Field(
        default=False,
        description="Placeholder the model could not draft; the founder must write it",
    )
    edited: bool = False


class InterviewScript(BaseModel):
    generated_at: datetime
    edited_at: datetime | None = None
    prompt_id: str | None = None
    model: str | None = None
    targets: list[ScriptTarget] = Field(default_factory=list)
    questions: list[ScriptQuestion] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def lint_count(self) -> int:
        return sum(1 for q in self.questions if q.lint)
