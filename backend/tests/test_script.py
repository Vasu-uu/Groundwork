import json
from datetime import UTC, datetime

import pytest

from app.llm import UsageTracker
from app.llm.mock import MockProvider
from app.models.analysis import AnalysisResult, ClusteringResult, Theme, VerdictLabel
from app.models.evidence import VerificationStats
from app.models.script import InterviewScript, ScriptQuestion, Section, TargetKind
from app.services.errors import InvalidInputError
from app.services.review import Decision, FinalDecision
from app.services.script import (
    LLMQuestion,
    QuestionEdit,
    apply_edits,
    assemble,
    draft_script,
    select_targets,
)


def decision(hid: str, final: VerdictLabel | None, reasoning: str = "") -> FinalDecision:
    return FinalDecision(
        hypothesis_id=hid,
        text=f"Hypothesis {hid}",
        ai_verdict=final or VerdictLabel.VALIDATED,
        final_verdict=final,
        decision=Decision.APPROVE if final else Decision.REJECT,
        reasoning=reasoning,
        note="",
        supporting=[],
        contradicting=[],
    )


def theme(tid: str, freq: int) -> Theme:
    return Theme(
        id=tid,
        label=f"Theme {tid}",
        description="",
        pain_point_ids=[],
        interview_ids=[f"I-{i}" for i in range(freq)],
        frequency=freq,
        share=freq / 6,
    )


def result(themes: list[Theme]) -> AnalysisResult:
    return AnalysisResult(
        run_id="r",
        interview_count=6,
        pain_points=[],
        rejected_quotes=[],
        quote_stats=VerificationStats(),
        clustering=ClusteringResult(themes=themes),
        verdicts=[],
    )


DECISIONS = [
    decision("H1", VerdictLabel.VALIDATED),
    decision("H2", VerdictLabel.MIXED),
    decision("H3", None, reasoning="Questions were leading."),
    decision("H4", VerdictLabel.UNTESTED),
    decision("H5", VerdictLabel.INVALIDATED),
]
THEMES = [theme("T1", 2), theme("T2", 5), theme("T3", 4), theme("T4", 1)]


def test_targets_are_open_hypotheses_and_top_themes():
    targets = select_targets(DECISIONS, result(THEMES))
    hyp = [t.id for t in targets if t.kind is TargetKind.HYPOTHESIS]
    themes = [t.id for t in targets if t.kind is TargetKind.THEME]
    assert hyp == ["H2", "H3", "H4"]  # settled H1 and H5 are not re-asked
    assert themes == ["T2", "T3", "T1"]  # three most frequent
    h3 = next(t for t in targets if t.id == "H3")
    assert "rejected" in h3.reason and "Questions were leading." in h3.reason


def test_assemble_orders_lints_and_fills_gaps():
    targets = select_targets(DECISIONS, result(THEMES[:1]))
    drafted = [
        LLMQuestion(target="H2", question="How do you decide which invoices to chase first?"),
        LLMQuestion(
            target="h4", question="Would you pay for automatic reminders?"
        ),  # case-insensitive
        LLMQuestion(target="T1", question="Tell me about the last time this happened."),
        LLMQuestion(target="H9", question="Unasked target?"),
        LLMQuestion(target="H2", question="Second for H2?"),
        LLMQuestion(target="H2", question="Third for H2 is dropped."),
    ]
    questions, warnings = assemble(targets, drafted)
    assert [(q.target, q.section) for q in questions] == [
        ("T1", Section.PAIN),
        ("H2", Section.HYPOTHESIS),
        ("H2", Section.HYPOTHESIS),
        ("H3", Section.HYPOTHESIS),
        ("H4", Section.HYPOTHESIS),
    ]
    assert [q.id for q in questions] == ["Q1", "Q2", "Q3", "Q4", "Q5"]
    placeholder = questions[3]
    assert placeholder.needs_edit and placeholder.question == ""
    assert any("Hypothetical" in issue for issue in questions[4].lint)
    assert any("H3" in w for w in warnings)
    assert any("Ignored 1" in w for w in warnings)


async def test_draft_script_with_model_output():
    reply = json.dumps(
        {
            "questions": [
                {
                    "target": t,
                    "question": f"Tell me about the last time {t} happened.",
                    "purpose": "p",
                    "bias_check": "b",
                    "follow_ups": "What happened next?",
                }
                for t in ("H2", "H3", "H4", "T2")
            ]
        }
    )
    tracker = UsageTracker("t")
    script = await draft_script(
        "Study", DECISIONS, result([THEMES[1]]), MockProvider([reply]), tracker=tracker
    )
    assert script.prompt_id == "draft_interview_script.v1"
    assert script.questions[0].section is Section.WARMUP
    assert script.questions[-1].section is Section.WRAPUP
    targeted = [q for q in script.questions if q.target]
    assert [q.target for q in targeted] == ["T2", "H2", "H3", "H4"]
    assert targeted[0].follow_ups == ["What happened next?"]
    assert all(not q.lint for q in script.questions)
    assert tracker.summary().calls == 1


async def test_unusable_model_output_degrades_to_placeholders():
    script = await draft_script(
        "Study", DECISIONS, result([]), MockProvider(["not json"] * 3), max_retries=2
    )
    targeted = [q for q in script.questions if q.target]
    assert targeted and all(q.needs_edit for q in targeted)
    assert any("unusable" in w for w in script.warnings)


def make_script() -> InterviewScript:
    return InterviewScript(
        generated_at=datetime.now(UTC),
        questions=[
            ScriptQuestion(id="Q1", section=Section.HYPOTHESIS, target="H2",
                           question="How do you pick?", bias_check="ok"),
            ScriptQuestion(id="Q2", section=Section.PAIN, target="T1",
                           question="Tell me about it.", bias_check="ok"),
        ],
    )  # fmt: skip


def test_founder_edits_reorder_rewrite_add_and_remove():
    edited = apply_edits(
        make_script(),
        [
            QuestionEdit(id="Q2", question="Tell me about it."),  # unchanged, moved first
            QuestionEdit(id="Q1", question="Don't you hate picking?"),  # rewritten
            QuestionEdit(question="What tools do you use today?", follow_ups=["Why that one?"]),
        ],
    )
    q2, q1, new = edited.questions
    assert q2.id == "Q2" and q2.bias_check == "ok" and not q2.edited
    assert q1.edited and q1.bias_check == "" and any("Leading" in i for i in q1.lint)
    assert new.id == "C1" and new.section is Section.CUSTOM and new.follow_ups == ["Why that one?"]
    assert edited.edited_at is not None


def test_edits_reject_empty_questions():
    with pytest.raises(InvalidInputError):
        apply_edits(make_script(), [QuestionEdit(id="Q1", question="  ")])
