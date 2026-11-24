import pytest

from app.services.question_lint import lint_question


def kinds(q: str) -> set[str]:
    return {issue.split(":")[0] for issue in lint_question(q)}


@pytest.mark.parametrize(
    "question",
    [
        "Tell me about the last time a client paid you late.",
        "How do you keep track of unpaid invoices today?",
        "Can you walk me through what happened after you sent the reminder?",
        "What did you do the last time a payment was overdue?",
    ],
)
def test_good_discovery_questions_pass(question):
    assert lint_question(question) == []


def test_leading_question_is_flagged():
    assert "Leading" in kinds("Don't you find chasing invoices takes too long?")
    assert "Leading" in kinds("Late payments are the worst part, right?")


def test_hypothetical_and_pitch_are_flagged():
    found = kinds("Would you pay for a tool that sends reminders automatically?")
    assert {"Hypothetical", "Pitches a solution"} <= found


def test_closed_question_is_flagged():
    assert "Closed" in kinds("Do you use spreadsheets for invoicing?")


def test_loaded_words_are_flagged():
    assert "Loaded wording" in kinds("What is the most frustrating part of invoicing?")


def test_double_barrelled_and_long_questions_are_flagged():
    assert "Double-barrelled" in kinds("How do you invoice? And how do you get paid?")
    long_q = "Tell me about " + " ".join(["the"] * 40) + " process."
    assert any(k.startswith("Long") for k in kinds(long_q))


def test_empty_question():
    assert lint_question("   ") == ["Empty question."]
