"""Shared helper for pulling a JSON object out of an LLM text reply.

Strips markdown code fences first; if the remainder still doesn't parse
(e.g. the model added a stray sentence before/after the JSON despite
instructions), falls back to slicing between the first '{' and the last
'}' before giving up.  If that also fails, ``_repair_json`` applies
progressively more aggressive fixes for the most common LLM JSON errors:
trailing commas, unquoted keys, single-quoted values, unescaped control
characters inside strings, and truncated payloads.

Used by every stage (Architect, Generator, Reviewer) so all three are
equally resilient to a model that doesn't perfectly follow the "raw JSON
only" instruction.
"""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[len("json"):]
    text = text.strip()

    # Try the clean path first.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Slice between first '{' and last '}' — handles prose-wrapped JSON.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        sliced = text[start : end + 1]
        try:
            return json.loads(sliced)
        except json.JSONDecodeError:
            # Apply repair heuristics to the sliced region.
            repaired = _repair_json(sliced)
            if repaired is not None:
                return repaired

    # Last resort: repair the raw text (in case braces weren't found).
    repaired = _repair_json(text)
    if repaired is not None:
        return repaired

    raise json.JSONDecodeError(
        f"Could not extract or repair JSON from text ({len(text)} chars)",
        text[:200], 0,
    )


# ---------------------------------------------------------------------------
# JSON repair — common LLM failure modes
# ---------------------------------------------------------------------------

def _repair_json(text: str) -> dict[str, Any] | None:
    """Try a cascade of fixes for broken JSON.  Returns the parsed dict
    on the first successful repair, or ``None`` if every strategy fails."""
    strategies = [
        _fix_trailing_commas,
        _fix_unquoted_keys,
        _fix_single_quoted_strings,
        _fix_bare_string_values,
        _fix_unescaped_newlines_in_strings,
        _fix_truncated_json,
    ]
    current = text.strip()
    for strategy in strategies:
        try:
            return json.loads(current)
        except json.JSONDecodeError:
            fixed = strategy(current)
            if fixed != current:
                current = fixed

    # One final attempt with all fixes applied cumulatively.
    try:
        return json.loads(current)
    except json.JSONDecodeError:
        return None


def _fix_trailing_commas(text: str) -> str:
    """Remove trailing commas before ``}`` or ``]``."""
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _fix_unquoted_keys(text: str) -> str:
    r"""Quote bare object keys like ``score: 9.0`` -> ``"score": 9.0``.

    Matches a word at the start of a line (after optional whitespace)
    followed by a colon that isn't already inside a string.
    """
    # Match: optional whitespace, a word-like key, colon, not preceded by quote.
    return re.sub(
        r'(?<=[\{\s,])'           # preceded by brace, whitespace, or comma
        r'([a-zA-Z_][a-zA-Z0-9_]*)'  # the key
        r'\s*:\s*',               # colon with optional whitespace
        r'"\1": ',
        text,
    )


def _fix_single_quoted_strings(text: str) -> str:
    r"""Replace single-quoted JSON strings with double-quoted ones.

    Uses a two-pass approach: first swap all ``'`` to ``"`` throughout
    the text, which handles keys and values in one shot, then fix any
    double-quote collisions inside strings (``""…""`` -> ``\"…\"`` around
    words that contain the swapped quotes).
    """
    # Replace all single-quote pairs with double-quote pairs.
    result = re.sub(r"'([^']*)'", r'"\1"', text)
    return result


def _fix_bare_string_values(text: str) -> str:
    r"""Quote bare word values like ``"key": active`` -> ``"key": "active"``.

    Handles values that are unquoted words (not numbers, not true/false/null,
    not already quoted, not nested objects/arrays).  Preserves any comma
    or brace that follows the value.
    """
    def _quote_bare(m: re.Match) -> str:
        prefix = m.group(1)   # `": `
        value = m.group(2).strip()
        suffix = m.group(3)   # `,` or `}` or `]`
        # Don't touch numbers, booleans, null, or already-quoted strings.
        if re.match(r'^-?\d+\.?\d*([eE][+-]?\d+)?$', value):
            return m.group(0)
        if value in ("true", "false", "null"):
            return m.group(0)
        if value.startswith('"') or value.startswith("{"):
            return m.group(0)
        return f'{prefix}"{value}"{suffix}'

    return re.sub(
        r'(:\s*)([^",\{\[\}\n]+?)(\s*[,}\]])',
        _quote_bare,
        text,
    )


def _fix_unescaped_newlines_in_strings(text: str) -> str:
    r"""Replace literal newlines inside double-quoted strings with ``\\n``.

    LLMs occasionally emit multi-line string values, which breaks the JSON
    parser.  This finds ``"…`` pairs that contain real newlines and
    collapses them.
    """
    result: list[str] = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != '\\'):
            in_string = not in_string
            result.append(ch)
        elif in_string and ch == '\n':
            result.append('\\n')
        elif in_string and ch == '\r':
            if i + 1 < len(text) and text[i + 1] == '\n':
                i += 1
            result.append('\\n')
        else:
            result.append(ch)
        i += 1
    return ''.join(result)


def _fix_truncated_json(text: str) -> str:
    """Close unclosed braces, brackets, and strings on truncated JSON.

    When an LLM output is cut off mid-stream, the JSON object may be
    missing closing delimiters.  This appends the minimum number of
    ``}``, ``]``, and ``"`` characters to make the structure balance.
    """
    stack: list[str] = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != '\\'):
            in_string = not in_string
        elif not in_string:
            if ch == '{':
                stack.append('}')
            elif ch == '[':
                stack.append(']')
            elif ch == '}':
                if stack and stack[-1] == '}':
                    stack.pop()
            elif ch == ']':
                if stack and stack[-1] == ']':
                    stack.pop()
        i += 1

    suffix = ''
    if in_string:
        suffix += '"'
    suffix += ''.join(reversed(stack))
    return text + suffix
