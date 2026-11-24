"""SQLite tables (SQLAlchemy 2.0).

Pydantic domain objects (transcripts, analysis results) are stored as JSON
columns: they are always read and written whole, and keeping one source of
truth for their shape (the Pydantic models) avoids a second schema to maintain.
The decision log is append-only: rows are inserted, never updated or deleted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class StudyRow(Base):
    """One discovery study: interviews + hypotheses, its analysis and review state."""

    __tablename__ = "studies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), index=True)
    progress: Mapped[str | None] = mapped_column(String(40), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    error_kind: Mapped[str | None] = mapped_column(String(40), default=None)
    sample_set: Mapped[str | None] = mapped_column(String(80), default=None)
    hypotheses: Mapped[list[Any]] = mapped_column(default=list)
    transcripts: Mapped[list[Any]] = mapped_column(default=list)
    result: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ReviewRow(Base):
    """The founder's current decision on one hypothesis verdict."""

    __tablename__ = "reviews"

    study_id: Mapped[str] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), primary_key=True
    )
    hypothesis_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    decision: Mapped[str] = mapped_column(String(20))
    ai_verdict: Mapped[str] = mapped_column(String(20))
    final_verdict: Mapped[str | None] = mapped_column(String(20), default=None)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    removed_evidence: Mapped[list[Any]] = mapped_column(default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DecisionLogRow(Base):
    """Append-only audit trail of what the AI suggested and what the founder decided."""

    __tablename__ = "decision_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    study_id: Mapped[str] = mapped_column(ForeignKey("studies.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(20))  # founder | ai | system
    action: Mapped[str] = mapped_column(String(40))
    hypothesis_id: Mapped[str | None] = mapped_column(String(20), default=None)
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)


class LLMCallRow(Base):
    """One model call, for the token counter and the AI Disclosure Statement."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    study_id: Mapped[str] = mapped_column(ForeignKey("studies.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str] = mapped_column(String(40))
    purpose: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(120))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float] = mapped_column(default=0.0)
    ok: Mapped[bool] = mapped_column(default=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
