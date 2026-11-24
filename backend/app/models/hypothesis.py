"""Founder hypotheses. Verdict models are added with hypothesis evaluation (Stage 4)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Hypothesis(BaseModel):
    id: str = Field(min_length=1, max_length=20)
    text: str = Field(min_length=3, max_length=500)
