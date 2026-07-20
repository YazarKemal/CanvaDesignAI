from src import orchestrator
from src.reviewer import ReviewResult

BRIEF = {"aspect_ratio": "1:1 (1080x1080)", "target_tool": "Canva Magic Media"}

CARD = {
    "concept": "Grand Opening Cafe",
    "prompt_text": "A minimalist flat vector espresso cup, terracotta palette, negative space at top.",
    "negative_prompt": "embedded text, watermark",
    "aspect_ratio": "1:1 (1080x1080)",
    "target_tool": "Canva Magic Media",
    "canva_tip": "Add your headline up top.",
    "art_direction": {"color_palette": ["terracotta", "cream", "espresso"], "lighting": "daylight", "mood": "minimalist"},
}


def _patch_stages(monkeypatch, review_fn):
    monkeypatch.setattr(orchestrator, "build_brief", lambda concept, **kw: BRIEF)
    monkeypatch.setattr(orchestrator, "generate_prompt", lambda brief, concept, feedback=None, **kw: CARD)
    monkeypatch.setattr(orchestrator, "review_prompt", review_fn)


def test_pipeline_passes_on_first_attempt(monkeypatch):
    _patch_stages(monkeypatch, lambda card, **kw: ReviewResult(score=9.0, passed=True, feedback=""))

    result = orchestrator.run_pipeline("Grand Opening Cafe")

    assert result.approved is True
    assert result.attempts == 1
    assert result.card == CARD
    assert result.brief == BRIEF


def test_pipeline_retries_then_passes(monkeypatch):
    calls = {"n": 0}

    def fake_review(card, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return ReviewResult(score=7.0, passed=False, feedback="Reserve more negative space.")
        return ReviewResult(score=9.0, passed=True, feedback="")

    _patch_stages(monkeypatch, fake_review)

    result = orchestrator.run_pipeline("Grand Opening Cafe", max_attempts=3)

    assert result.approved is True
    assert result.attempts == 2
    assert calls["n"] == 2


def test_pipeline_exhausts_attempts_returns_best_effort(monkeypatch):
    _patch_stages(monkeypatch, lambda card, **kw: ReviewResult(score=6.0, passed=False, feedback="Too generic."))

    result = orchestrator.run_pipeline("Grand Opening Cafe", max_attempts=2)

    assert result.approved is False
    assert result.attempts == 2
    assert len(result.history) == 2
