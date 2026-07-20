from src import orchestrator
from src.reviewer import ReviewResult

DRAFT = {
    "theme": "Modern Cafe",
    "color_palette": ["#4A2E1B", "#F5EFE6", "#D4A373"],
    "typography": {"headline": "Montserrat Bold", "body_text": "Join us!"},
    "image_prompts": {"main_visual": "A latte with micro-foam art."},
    "layout_instructions": "Top 40% text, bottom 60% visual.",
}


def test_pipeline_passes_on_first_attempt(monkeypatch):
    monkeypatch.setattr(orchestrator, "generate_design", lambda concept, feedback=None, **kw: DRAFT)
    monkeypatch.setattr(
        orchestrator, "review_design", lambda draft, **kw: ReviewResult(score=9.0, passed=True, feedback="")
    )

    result = orchestrator.run_pipeline("Grand Opening Cafe")

    assert result.approved is True
    assert result.attempts == 1
    assert result.design == DRAFT


def test_pipeline_retries_then_passes(monkeypatch):
    calls = {"n": 0}

    def fake_review(draft, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return ReviewResult(score=4.0, passed=False, feedback="Fix contrast.")
        return ReviewResult(score=8.5, passed=True, feedback="")

    monkeypatch.setattr(orchestrator, "generate_design", lambda concept, feedback=None, **kw: DRAFT)
    monkeypatch.setattr(orchestrator, "review_design", fake_review)

    result = orchestrator.run_pipeline("Grand Opening Cafe", max_attempts=3)

    assert result.approved is True
    assert result.attempts == 2
    assert calls["n"] == 2


def test_pipeline_exhausts_attempts_returns_best_effort(monkeypatch):
    monkeypatch.setattr(orchestrator, "generate_design", lambda concept, feedback=None, **kw: DRAFT)
    monkeypatch.setattr(
        orchestrator, "review_design", lambda draft, **kw: ReviewResult(score=3.0, passed=False, feedback="Bad.")
    )

    result = orchestrator.run_pipeline("Grand Opening Cafe", max_attempts=2)

    assert result.approved is False
    assert result.attempts == 2
    assert len(result.history) == 2
