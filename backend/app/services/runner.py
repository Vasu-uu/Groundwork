"""Runs analyses in the background and records the outcome.

The API marks a study `analyzing` and returns immediately; this runner does
the work, writes progress steps for the UI to poll, keeps a live usage
counter, and maps failures to explicit, user-facing error kinds:

    provider_unavailable  model server down, timeout, rate limit
    provider_config       missing API key, model not pulled
    model_output          the model kept returning unusable output
    invalid_input         nothing analysable in the study
    internal              a bug; details are in the server log
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session, sessionmaker

from app.llm import (
    GenerationOptions,
    LLMError,
    LLMProvider,
    ProviderConfigError,
    ProviderUnavailableError,
    UsageSummary,
    UsageTracker,
)
from app.services import studies
from app.services.analysis import AnalysisConfig, AnalysisInputError, run_analysis

logger = logging.getLogger("groundwork.runner")


def error_kind(exc: Exception) -> str:
    if isinstance(exc, ProviderUnavailableError):
        return "provider_unavailable"
    if isinstance(exc, ProviderConfigError):
        return "provider_config"
    if isinstance(exc, LLMError):
        return "model_output"
    if isinstance(exc, AnalysisInputError):
        return "invalid_input"
    return "internal"


class AnalysisRunner:
    def __init__(
        self,
        provider: LLMProvider,
        session_factory: sessionmaker[Session],
        *,
        options: GenerationOptions | None = None,
        config: AnalysisConfig | None = None,
    ) -> None:
        self.provider = provider
        self.session_factory = session_factory
        self.options = options
        self.config = config or AnalysisConfig()
        self._live: dict[str, UsageTracker] = {}

    def live_usage(self, study_id: str) -> UsageSummary | None:
        """Token usage of a run still in progress (None when nothing is running)."""
        tracker = self._live.get(study_id)
        return tracker.summary() if tracker else None

    async def run(self, study_id: str) -> None:
        run_id = uuid.uuid4().hex[:12]
        tracker = UsageTracker(run_id)
        self._live[study_id] = tracker
        try:
            with self.session_factory() as db:
                row = studies.get_study(db, study_id)
                corpus = studies.corpus_of(row)
                hypotheses = studies.hypotheses_of(row)

            def progress(step: str) -> None:
                with self.session_factory.begin() as db:
                    studies.set_progress(db, studies.get_study(db, study_id), step)

            try:
                result = await run_analysis(
                    corpus,
                    hypotheses,
                    self.provider,
                    options=self.options,
                    tracker=tracker,
                    config=self.config,
                    run_id=run_id,
                    on_progress=progress,
                )
            except Exception as exc:  # noqa: BLE001 - every failure must reach the UI
                kind = error_kind(exc)
                if kind == "internal":
                    logger.exception("analysis crashed for study %s", study_id)
                    message = "Something went wrong on our side. Check the server log."
                else:
                    message = str(exc)
                with self.session_factory.begin() as db:
                    studies.save_calls(db, study_id, run_id, tracker.records)
                    studies.fail_analysis(db, studies.get_study(db, study_id), kind, message)
                return

            with self.session_factory.begin() as db:
                studies.save_calls(db, study_id, run_id, tracker.records)
                studies.complete_analysis(db, studies.get_study(db, study_id), result)
        finally:
            self._live.pop(study_id, None)
