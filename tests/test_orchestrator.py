from src import orchestrator
from src.reviewer import ReviewResult

DRAFT = {
    "concept": "Grand Opening Cafe",
    "image_prompt": "A flat-white with rosetta latte art, photography, golden-hour light, warm tones.",
    "negative_prompt": "text, watermark",
    "art_direction": {
        "medium": "photography",
        "composition": "rule of thirds",
        "lighting": "golden hour",
        "color_palette": ["#4A2E1B", "#D4A373", "#F5EFE6"],
        "mood": "cozy",
    },
    "aspect_ratio": "4:5",
    "target_tools": ["DALL-E 3"],
}


def test_pipeline_passes_on_first_attempt(monkeypatch):
    monkeypatch.setattr(orchestrator, "generate_prompt", lambda concept, feedback=None, **kw: DRAFT)
    monkeypatch.setattr(
        orchestrator, "review_prompt", lambda draft, **kw: ReviewResult(score=9.0, passed=True, feedback="")
    )

    result = orchestrator.run_pipeline("Grand Opening Cafe")

    assert result.approved is True
    assert result.attempts == 1
    assert result.prompt == DRAFT


def test_pipeline_retries_then_passes(monkeypatch):
    calls = {"n": 0}

    def fake_review(draft, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return ReviewResult(score=4.0, passed=False, feedback="Specify a camera and lens.")
        return ReviewResult(score=8.5, passed=True, feedback="")

    monkeypatch.setattr(orchestrator, "generate_prompt", lambda concept, feedback=None, **kw: DRAFT)
    monkeypatch.setattr(orchestrator, "review_prompt", fake_review)

    result = orchestrator.run_pipeline("Grand Opening Cafe", max_attempts=3)

    assert result.approved is True
    assert result.attempts == 2
    assert calls["n"] == 2


def test_pipeline_exhausts_attempts_returns_best_effort(monkeypatch):
    monkeypatch.setattr(orchestrator, "generate_prompt", lambda concept, feedback=None, **kw: DRAFT)
    monkeypatch.setattr(
        orchestrator, "review_prompt", lambda draft, **kw: ReviewResult(score=3.0, passed=False, feedback="Too vague.")
    )

    result = orchestrator.run_pipeline("Grand Opening Cafe", max_attempts=2)

    assert result.approved is False
    assert result.attempts == 2
    assert len(result.history) == 2
