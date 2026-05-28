"""Unit tests for src.preparation.screening.generate_screening_answers.

TDD RED phase — these tests define the contract for the shared screening function
extracted from application.py. The tests mock the Anthropic client to avoid
live API calls.

Tests:
    test_returns_answers_list          — valid Haiku response returns list of {question, answer} dicts
    test_empty_questions_returns_empty — empty questions list returns [] without calling Anthropic
    test_fenced_json_block_parsed      — markdown-fenced ```json response is parsed correctly
    test_route_delegates_to_shared_fn  — the existing FastAPI route delegates to the shared function
"""

import json
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Test 1: valid response returns list of {question, answer} dicts
# ---------------------------------------------------------------------------


def test_returns_answers_list() -> None:
    """generate_screening_answers returns a list of {question, answer} dicts
    matching the length of questions when Haiku returns valid JSON.
    """
    from src.preparation.screening import generate_screening_answers

    questions = ["Are you authorized to work in the US?", "Years of Python experience?"]
    mock_response_text = json.dumps(
        {
            "answers": [
                {"question": "Are you authorized to work in the US?", "answer": "Yes"},
                {"question": "Years of Python experience?", "answer": "5"},
            ]
        }
    )

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=mock_response_text)]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("src.preparation.screening.anthropic.Anthropic", return_value=mock_client):
        profile_config = MagicMock()
        profile_config.summary = "Experienced engineer"
        profile_config.skills = ["Python", "FastAPI"]
        profile_config.key_projects = []

        result = generate_screening_answers(
            profile_config=profile_config,
            job_title="Software Engineer",
            job_description="Build APIs with Python",
            questions=questions,
        )

    assert isinstance(result, list), "Result must be a list"
    assert len(result) == 2, "Result length must match questions length"
    for item in result:
        assert "question" in item, "Each item must have 'question'"
        assert "answer" in item, "Each item must have 'answer'"


# ---------------------------------------------------------------------------
# Test 2: empty questions returns [] without calling Anthropic
# ---------------------------------------------------------------------------


def test_empty_questions_returns_empty() -> None:
    """Empty questions list returns [] without invoking the Anthropic client."""
    from src.preparation.screening import generate_screening_answers

    mock_client = MagicMock()

    with patch("src.preparation.screening.anthropic.Anthropic", return_value=mock_client):
        profile_config = MagicMock()
        result = generate_screening_answers(
            profile_config=profile_config,
            job_title="Engineer",
            job_description="Build things",
            questions=[],
        )

    assert result == [], "Empty questions must return empty list"
    mock_client.messages.create.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: fenced ```json block is parsed correctly (markdown-fallback regression)
# ---------------------------------------------------------------------------


def test_fenced_json_block_parsed() -> None:
    """When the model returns a ```json fenced block, the inner JSON is extracted and parsed."""
    from src.preparation.screening import generate_screening_answers

    questions = ["Do you have a degree?"]
    fenced_response = (
        '```json\n'
        '{"answers": [{"question": "Do you have a degree?", "answer": "Yes, Computer Science"}]}\n'
        '```'
    )

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=fenced_response)]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("src.preparation.screening.anthropic.Anthropic", return_value=mock_client):
        profile_config = MagicMock()
        profile_config.summary = "Graduate"
        profile_config.skills = []
        profile_config.key_projects = []

        result = generate_screening_answers(
            profile_config=profile_config,
            job_title="Engineer",
            job_description="Build software",
            questions=questions,
        )

    assert len(result) == 1, "Fenced JSON must be parsed to produce one answer"
    assert result[0]["answer"] == "Yes, Computer Science"


# ---------------------------------------------------------------------------
# Test 4: existing FastAPI route delegates to the shared function
# ---------------------------------------------------------------------------


def test_route_imports_shared_function() -> None:
    """The application.py route must import generate_screening_answers from screening.py."""
    import importlib
    import ast
    import pathlib

    route_path = pathlib.Path(
        "src/api/routes/application.py"
    )
    source = route_path.read_text()
    # Check for the import statement
    assert "from src.preparation.screening import generate_screening_answers" in source, (
        "application.py must import generate_screening_answers from src.preparation.screening"
    )
