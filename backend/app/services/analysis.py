"""End-to-end analysis pipeline, up to (not past) the human checkpoint.

    corpus --extract--> verified pain points --cluster--> themes
           --assess---> per-interview stances --rules--> verdict suggestions

The result holds AI suggestions only. Nothing downstream (next interview
script, export) may run until the founder reviews them; that gate is enforced
by the API (Stage 5).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from app.config import Settings
from app.llm import GenerationOptions, LLMError, LLMProvider, UsageTracker
from app.models.analysis import AnalysisResult
from app.models.hypothesis import Hypothesis
from app.services.assessment import assess_corpus
from app.services.clustering import ClusterConfig, cluster_pain_points
from app.services.corpus import Corpus
from app.services.extraction import ExtractionConfig, extract_corpus
from app.services.verdicts import build_verdict

MAX_HYPOTHESES = 10

ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class AnalysisConfig:
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    clustering: ClusterConfig = field(default_factory=ClusterConfig)

    @classmethod
    def from_settings(cls, s: Settings) -> AnalysisConfig:
        return cls(
            extraction=ExtractionConfig.from_settings(s),
            clustering=ClusterConfig(max_retries=s.llm_max_retries),
        )


class AnalysisModelError(LLMError):
    """The model returned unusable output for every interview: there are no results."""


class AnalysisInputError(ValueError):
    """The analysis request itself is unusable (user-facing message)."""


def validate_inputs(corpus: Corpus, hypotheses: list[Hypothesis]) -> None:
    if not corpus.transcripts:
        raise AnalysisInputError("Add at least one interview.")
    if not any(t.evidence_segments for t in corpus.transcripts):
        raise AnalysisInputError("None of the interviews contains customer speech to analyse.")
    if not hypotheses:
        raise AnalysisInputError("Add at least one hypothesis to test.")
    if len(hypotheses) > MAX_HYPOTHESES:
        raise AnalysisInputError(f"Test at most {MAX_HYPOTHESES} hypotheses per run.")
    ids = [h.id for h in hypotheses]
    if len(set(ids)) != len(ids):
        raise AnalysisInputError("Hypothesis IDs must be unique.")


async def run_analysis(
    corpus: Corpus,
    hypotheses: list[Hypothesis],
    provider: LLMProvider,
    *,
    options: GenerationOptions | None = None,
    tracker: UsageTracker | None = None,
    config: AnalysisConfig | None = None,
    run_id: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> AnalysisResult:
    """Run the full analysis. Raises `AnalysisInputError` or provider `LLMError`s."""
    validate_inputs(corpus, hypotheses)
    config = config or AnalysisConfig()
    run_id = run_id or uuid.uuid4().hex[:12]
    tracker = tracker or UsageTracker(run_id)
    progress = on_progress or (lambda _step: None)

    progress("extracting")
    extraction = await extract_corpus(
        corpus, provider, options=options, tracker=tracker, config=config.extraction
    )
    progress("clustering")
    clustering = await cluster_pain_points(
        extraction.pain_points,
        corpus.interview_count,
        provider,
        options=options,
        tracker=tracker,
        config=config.clustering,
    )
    progress("assessing")
    assessment = await assess_corpus(
        corpus, hypotheses, provider, options=options, tracker=tracker, config=config.extraction
    )
    usable = [t for t in corpus.transcripts if t.evidence_segments]
    extraction_failed = {f.interview_id for f in extraction.failures}
    if (
        usable
        and not extraction.pain_points
        and extraction_failed >= {t.id for t in usable}
        and set(assessment.failed_interviews) >= {t.id for t in usable}
    ):
        # Empty results must not be shown as findings ("no pain points").
        raise AnalysisModelError(
            "The model returned unusable output for every interview, even after retries. "
            "Try again, or use a larger model."
        )

    progress("deciding")
    verdicts = [
        build_verdict(
            h,
            assessment.assessments,
            small_sample=corpus.small_sample,
            themes=clustering.themes,
            pain_points=extraction.pain_points,
            failed_interviews=len(assessment.failed_interviews),
        )
        for h in hypotheses
    ]

    warnings = list(corpus.warnings) + clustering.notes
    failures = [f"{f.interview_id} {f.segments}: {f.error}" for f in extraction.failures]
    failures += assessment.failures
    if failures:
        warnings.append(
            f"{len(failures)} model call(s) returned unusable output after retries; "
            "the affected parts are missing from the analysis."
        )
    progress("done")
    return AnalysisResult(
        run_id=run_id,
        interview_count=corpus.interview_count,
        warnings=warnings,
        pain_points=extraction.pain_points,
        rejected_quotes=extraction.rejected + assessment.rejected,
        quote_stats=extraction.stats + assessment.stats,
        clustering=clustering,
        verdicts=verdicts,
        failures=failures,
        # Prompt versions actually called in this run (purposes start with the prompt ID).
        prompt_ids=sorted({r.purpose.split(":")[0] for r in tracker.records}),
    )
