import json

import pytest

from src.llm_json import (
    _fix_bare_string_values,
    _fix_single_quoted_strings,
    _fix_trailing_commas,
    _fix_truncated_json,
    _fix_unescaped_newlines_in_strings,
    _fix_unquoted_keys,
    extract_json,
)

VALID = '{"score": 9.0, "criteria_scores": {}, "feedback": ""}'


# -- extract_json — clean paths ------------------------------------------------


def test_extract_json_clean():
    assert extract_json(VALID) == {"score": 9.0, "criteria_scores": {}, "feedback": ""}


def test_extract_json_strips_markdown_fences():
    assert extract_json(f"```json\n{VALID}\n```") == json.loads(VALID)


def test_extract_json_extracts_from_prose_wrapper():
    wrapped = "Sure, here is the data:\n" + VALID + "\nLet me know!"
    assert extract_json(wrapped) == json.loads(VALID)


# -- Individual repair strategies ----------------------------------------------


def test_fix_trailing_commas():
    assert _fix_trailing_commas('{"a": 1,}') == '{"a": 1}'
    assert _fix_trailing_commas('{"a": [1, 2,], "b": 3,}') == '{"a": [1, 2], "b": 3}'


def test_fix_unquoted_keys():
    fixed = _fix_unquoted_keys('{score: 9.0, feedback: "ok"}')
    assert '"score"' in fixed
    assert '"feedback"' in fixed
    assert json.loads(fixed)


def test_fix_single_quoted_strings():
    fixed = _fix_single_quoted_strings("{'score': 9.0, 'feedback': 'looks good'}")
    assert "'" not in fixed
    assert json.loads(fixed)


def test_fix_bare_string_values():
    fixed = _fix_bare_string_values('{"status": active, "count": 5}')
    assert json.loads(fixed)
    parsed = json.loads(fixed)
    assert parsed["status"] == "active"
    assert parsed["count"] == 5


def test_fix_unescaped_newlines():
    broken = '{"feedback": "line one\nline two\nline three"}'
    fixed = _fix_unescaped_newlines_in_strings(broken)
    assert "\n" not in fixed
    assert "\\n" in fixed
    parsed = json.loads(fixed)
    assert parsed["feedback"] == "line one\nline two\nline three"


def test_fix_truncated_missing_brace():
    truncated = '{"score": 9.0, "feedback": "ok"'
    fixed = _fix_truncated_json(truncated)
    assert fixed.endswith("}")
    assert json.loads(fixed)


def test_fix_truncated_missing_brace_and_string_quote():
    truncated = '{"score": 9.0, "feedback": "ok'
    fixed = _fix_truncated_json(truncated)
    assert json.loads(fixed)


def test_fix_truncated_nested_braces():
    truncated = '{"score": 9.0, "criteria_scores": {"a": 1'
    fixed = _fix_truncated_json(truncated)
    assert json.loads(fixed)


# -- End-to-end repair via extract_json ----------------------------------------


def test_extract_json_repairs_trailing_comma():
    assert extract_json('{"score": 9.0, "feedback": "ok",}') == {
        "score": 9.0,
        "feedback": "ok",
    }


def test_extract_json_repairs_unquoted_keys():
    assert extract_json('{score: 9.0, feedback: "ok"}') == {
        "score": 9.0,
        "feedback": "ok",
    }


def test_extract_json_repairs_single_quotes():
    assert extract_json("{'score': 8.5, 'feedback': 'add space'}") == {
        "score": 8.5,
        "feedback": "add space",
    }


def test_extract_json_repairs_combined_errors():
    """Trailing comma + unquoted key + single-quoted value: all fixed."""
    broken = "{score: 9.2, feedback: 'nice work',}"
    result = extract_json(broken)
    assert result["score"] == 9.2
    assert result["feedback"] == "nice work"


def test_extract_json_handles_truncated_input():
    truncated = '{"score": 9.0, "criteria_scores": {"concept_fidelity": 9.5'
    result = extract_json(truncated)
    assert result["score"] == 9.0
    assert result["criteria_scores"]["concept_fidelity"] == 9.5


def test_extract_json_handles_multi_line_string_value():
    broken = '{"score": 9.0,\n"feedback": "Line one\nLine two"}'
    result = extract_json(broken)
    assert result["feedback"] == "Line one\nLine two"


def test_extract_json_raises_on_garbage():
    with pytest.raises(json.JSONDecodeError):
        extract_json("not json at all just random words")


def test_extract_json_raises_on_empty_string():
    with pytest.raises(json.JSONDecodeError):
        extract_json("")


# -- Reviewer-format specific repairs ------------------------------------------


def test_extract_reviewer_json_with_broken_criteria_scores():
    """Simulate a Reviewer reply where criteria_scores has trailing comma
    and an unquoted value."""
    broken = (
        '{\n'
        '  score: 8.7,\n'
        '  criteria_scores: {\n'
        "    concept_fidelity: 9.0,\n"
        "    format_discipline: 10.0,\n"
        '  },\n'
        "  feedback: 'Reserve more negative space at the top.',\n"
        '}'
    )
    result = extract_json(broken)
    assert result["score"] == 8.7
    assert result["criteria_scores"]["concept_fidelity"] == 9.0
    assert result["criteria_scores"]["format_discipline"] == 10.0
    assert "negative space" in result["feedback"]
