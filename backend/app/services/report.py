"""Export an approved study as a Markdown or PDF report.

The report is built once as a list of simple blocks (headings, paragraphs,
bullets, quotes), then rendered to either format, so both always contain the
same content: the founder's decisions with their evidence (every quote with its
interview, speaker and segment), the pain themes, the next interview script,
the decision log, and run statistics for the AI disclosure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from fpdf import FPDF
from sqlalchemy.orm import Session

from app import __version__
from app.db.models import DecisionLogRow, StudyRow, utcnow
from app.llm.usage import UsageSummary
from app.models.analysis import AnalysisResult
from app.models.evidence import Evidence
from app.models.script import InterviewScript, Section
from app.services.review import FinalDecision, final_decisions
from app.services.script import get_script
from app.services.studies import decision_log, result_of, usage_of

Kind = Literal["title", "h2", "h3", "p", "meta", "bullet", "sub", "quote", "warn"]

MAX_QUOTES_PER_SIDE = 5
MAX_THEME_QUOTES = 3

SECTION_TITLE = {
    Section.WARMUP: "Warm-up",
    Section.PAIN: "Pain follow-ups",
    Section.HYPOTHESIS: "Hypotheses to test",
    Section.CUSTOM: "Your own questions",
    Section.WRAPUP: "Wrap-up",
}


@dataclass(frozen=True)
class Block:
    kind: Kind
    text: str
    cite: str = ""


def _cite(e: Evidence) -> str:
    parts = [e.speaker, e.interview_id, f"segment S{e.segment}"]
    if e.paraphrase:
        parts.append("founder notes, paraphrase")
    if e.match.value == "fuzzy":
        parts.append(f"fuzzy match {round(e.score * 100)}%")
    return ", ".join(parts)


def _quote(e: Evidence) -> Block:
    return Block("quote", " ".join(e.quote.split()), _cite(e))


def _fmt_time(at: datetime | None) -> str:
    return at.strftime("%Y-%m-%d %H:%M UTC") if at else "n/a"


def describe_log(e: DecisionLogRow) -> str:
    """One readable line for a decision-log entry."""
    d = e.details or {}
    label = e.action.replace("_", " ")
    if e.action == "review_saved" and isinstance(d.get("after"), dict):
        after = d["after"]
        final = after.get("final_verdict") or "re-test"
        why = f': "{after["reasoning"]}"' if after.get("reasoning") else ""
        decision, ai = after.get("decision"), d.get("ai_suggestion")
        return f"{e.hypothesis_id}: {decision} (AI suggested {ai}, final {final}){why}"
    if e.action == "approved" and isinstance(d.get("final_verdicts"), dict):
        verdicts = ", ".join(f"{h} {v or 're-test'}" for h, v in d["final_verdicts"].items())
        return f"checkpoint approved: {verdicts}"
    if e.action == "analysis_completed":
        return f"analysis completed: {d.get('pain_points')} pain points, {d.get('verified_quotes')}"
    if e.action == "analysis_failed":
        return f"analysis failed ({d.get('kind')}): {d.get('error')}"
    if e.action in ("script_generated", "script_edited"):
        return f"{label}: {d.get('questions')} questions, {d.get('flagged')} flagged"
    if d.get("reason"):
        return f"{label}: {d['reason']}"
    return label


def build_report(
    row: StudyRow,
    result: AnalysisResult,
    decisions: list[FinalDecision],
    script: InterviewScript | None,
    log: list[DecisionLogRow],
    usage: UsageSummary,
    *,
    generated_at: datetime | None = None,
) -> list[Block]:
    b: list[Block] = []
    add = b.append
    add(Block("title", f"Groundwork report: {row.name}"))
    add(
        Block(
            "meta",
            f"Generated {_fmt_time(generated_at or utcnow())} by Groundwork {__version__}. "
            f"{result.interview_count} interviews, approved {_fmt_time(row.approved_at)}.",
        )
    )
    add(
        Block(
            "p",
            "Verdicts were suggested by an AI model from verified verbatim quotes, then reviewed "
            "and approved by the founder. The founder's decision is final; the AI suggestion is "
            "shown for transparency.",
        )
    )
    for w in result.warnings:
        add(Block("warn", w))

    # Summary
    add(Block("h2", "Summary"))
    for d in decisions:
        final = d.final_verdict.value if d.final_verdict else "RE-TEST (evidence rejected)"
        ai = "" if d.final_verdict == d.ai_verdict else f" (AI suggested {d.ai_verdict.value})"
        add(Block("bullet", f"{d.hypothesis_id} {final}{ai}: {d.text}"))

    # Decisions with evidence
    add(Block("h2", "Decisions and evidence"))
    verdicts = {v.hypothesis.id: v for v in result.verdicts}
    for d in decisions:
        v = verdicts[d.hypothesis_id]
        add(Block("h3", f"{d.hypothesis_id}: {d.text}"))
        final = d.final_verdict.value if d.final_verdict else "re-test"
        add(
            Block(
                "p",
                f"Founder decision: {d.decision.value}, final verdict {final}. "
                f"AI suggestion: {d.ai_verdict.value} ({v.confidence.value} confidence). "
                f"{v.counts.supports} supported, {v.counts.contradicts} contradicted, "
                f"{v.counts.mixed} mixed, {v.counts.not_discussed} did not discuss it.",
            )
        )
        if d.reasoning:
            add(Block("p", f"Founder's reasoning: {d.reasoning}"))
        if d.note:
            add(Block("p", f"Note: {d.note}"))
        add(Block("p", f"What would change the AI suggestion: {v.what_would_change}"))
        for title, quotes in (("Supporting", d.supporting), ("Contradicting", d.contradicting)):
            if quotes:
                shown = quotes[:MAX_QUOTES_PER_SIDE]
                more = (
                    f" (showing {len(shown)} of {len(quotes)})" if len(quotes) > len(shown) else ""
                )
                add(Block("p", f"{title} quotes{more}:"))
                b.extend(_quote(e) for e in shown)
            else:
                add(Block("p", f"{title} quotes: none."))

    # Pain themes
    add(Block("h2", "Pain themes"))
    points = {p.id: p for p in result.pain_points}
    if not result.clustering.themes:
        add(Block("p", "No verified pain points were found."))
    for t in result.clustering.themes:
        add(
            Block(
                "h3", f"{t.id}: {t.label} ({t.frequency} of {result.interview_count} interviewees)"
            )
        )
        if t.description and t.description != t.label:
            add(Block("p", t.description))
        for pid in t.pain_point_ids[:MAX_THEME_QUOTES]:
            if pid in points:
                b.append(_quote(points[pid].evidence))

    # Script
    add(Block("h2", "Next interview script"))
    if script is None:
        add(Block("p", "No script has been generated yet."))
    else:
        for w in script.warnings:
            add(Block("warn", w))
        for section in SECTION_TITLE:
            qs = [q for q in script.questions if q.section is section]
            if not qs:
                continue
            add(Block("h3", SECTION_TITLE[section]))
            for q in qs:
                target = f" [{q.target}]" if q.target else ""
                text = q.question or "(to be written)"
                add(Block("bullet", f"{q.id}{target}: {text}"))
                if q.purpose:
                    add(Block("sub", f"Purpose: {q.purpose}"))
                if q.bias_check:
                    add(Block("sub", f"Bias check: {q.bias_check}"))
                for f in q.follow_ups:
                    add(Block("sub", f"Follow-up: {f}"))
                for issue in q.lint:
                    add(Block("sub", f"Wording problem: {issue}"))

    # Decision log
    add(Block("h2", "Decision log"))
    for e in log:
        add(Block("bullet", f"{_fmt_time(e.at)} [{e.actor}] {describe_log(e)}"))

    # Run statistics for the AI disclosure
    add(Block("h2", "AI usage"))
    stats = result.quote_stats
    add(
        Block(
            "bullet",
            f"Models: {', '.join(usage.models) or 'none'} "
            f"via {', '.join(usage.providers) or 'none'}",
        )
    )
    add(
        Block(
            "bullet",
            f"Model calls: {usage.calls} ({usage.failed_calls} failed); tokens: "
            f"{usage.prompt_tokens} prompt + {usage.completion_tokens} completion "
            f"= {usage.total_tokens}",
        )
    )
    add(Block("bullet", "Cost: 0 EUR (free, open-weight or free-tier models only)"))
    add(
        Block(
            "bullet",
            f"Quote verification: {stats.verified}/{stats.proposed} verified "
            f"({stats.exact} exact, {stats.fuzzy} fuzzy); "
            f"{stats.rejected} rejected and never used as evidence",
        )
    )
    prompts = sorted(
        set(result.prompt_ids) | ({script.prompt_id} if script and script.prompt_id else set())
    )
    add(Block("bullet", f"Prompts: {', '.join(prompts) or 'none'}"))
    return b


def report_for_study(db: Session, row: StudyRow) -> list[Block]:
    decisions = final_decisions(db, row)  # enforces the checkpoint
    result = result_of(row)
    assert result is not None
    return build_report(
        row, result, decisions, get_script(db, row), decision_log(db, row.id), usage_of(db, row.id)
    )


# --- Markdown ---------------------------------------------------------------------------------


def _md_escape_line(text: str) -> str:
    # Keep user text from turning into headings or list items.
    return "\\" + text if text[:1] in "#>-*+" else text


def to_markdown(blocks: list[Block]) -> str:
    out: list[str] = []
    prev: Kind | None = None
    for blk in blocks:
        t = blk.text
        if prev in ("bullet", "sub") and blk.kind not in ("bullet", "sub"):
            out.append("")  # end the list
        match blk.kind:
            case "title":
                out.append(f"# {t}\n")
            case "h2":
                out.append(f"\n## {t}\n")
            case "h3":
                out.append(f"\n### {t}\n")
            case "meta":
                out.append(f"*{t}*\n")
            case "p":
                out.append(_md_escape_line(t) + "\n")
            case "bullet":
                out.append(f"- {t}")
            case "sub":
                out.append(f"  - {t}")
            case "warn":
                out.append(f"> **Warning:** {t}\n")
            case "quote":
                out.append(f'> "{t}"  \n> — {blk.cite}\n')
        prev = blk.kind
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


# --- PDF --------------------------------------------------------------------------------------

# Typography the built-in PDF fonts cannot encode, mapped to ASCII.
_ASCII = str.maketrans(
    {
        0x2018: "'",
        0x2019: "'",
        0x201C: '"',
        0x201D: '"',
        0x2013: "-",
        0x2014: "-",
        0x2026: "...",
        0x2022: "-",
        0x00A0: " ",
        0x202F: " ",
        0x2192: "->",
    }
)


def _pdf_text(text: str) -> str:
    """The PDF uses built-in fonts (Latin-1 only); map common typography, replace the rest."""
    return text.translate(_ASCII).encode("latin-1", "replace").decode("latin-1")


def to_pdf(blocks: list[Block]) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_title(_pdf_text(blocks[0].text if blocks else "Groundwork report"))
    pdf.set_creator("Groundwork")
    pdf.add_page()
    width = pdf.epw

    def write(text: str, *, size: float, style: str = "", h: float = 5.5, indent: float = 0,
              color: tuple[int, int, int] = (30, 30, 30), gap: float = 1.5) -> None:  # fmt: skip
        pdf.set_font("Helvetica", style, size)
        pdf.set_text_color(*color)
        pdf.set_x(pdf.l_margin + indent)
        pdf.multi_cell(width - indent, h, _pdf_text(text), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(gap)

    for blk in blocks:
        match blk.kind:
            case "title":
                write(blk.text, size=18, style="B", h=8, color=(15, 70, 65), gap=2)
            case "h2":
                pdf.ln(3)
                write(blk.text, size=14, style="B", h=7, color=(15, 70, 65))
            case "h3":
                pdf.ln(1)
                write(blk.text, size=11.5, style="B", h=6)
            case "meta":
                write(blk.text, size=9, style="I", color=(100, 100, 100))
            case "p":
                write(blk.text, size=10)
            case "bullet":
                write("- " + blk.text, size=10, indent=3, gap=0.8)
            case "sub":
                write(blk.text, size=9, indent=8, gap=0.5, color=(80, 80, 80))
            case "warn":
                write("Warning: " + blk.text, size=9.5, style="I", indent=3, color=(150, 80, 0))
            case "quote":
                write(f'"{blk.text}"', size=10, style="I", indent=6, gap=0.3)
                write(blk.cite, size=8.5, indent=6, color=(110, 110, 110))
    return bytes(pdf.output())
