import pytest

from src import orchestrator
from src.brand_profiles import BrandNotFoundError, load_brand
from src.orchestrator import PipelineError
from src.reviewer import ReviewResult
from src.schema import PromptValidationError
from src.style_presets import StyleNotFoundError, load_style

BRIEF = {"aspect_ratio": "1:1 (1080x1080)", "target_tool": "Canva Magic Media"}

CARD = {
    "concept": "Grand Opening Cafe",
    "magic_media_prompt": "A minimalist flat vector espresso cup, terracotta palette, negative space at top.",
    "negative_prompt": "embedded text, watermark",
    "aspect_ratio": "1:1 (1080x1080)",
    "target_tool": "Canva Magic Media",
    "layer_typography_architecture": {
        "headline": "Grand Opening",
        "subtext": "Freshly roasted, every morning.",
        "color_palette": ["#4A2E1B", "#D4A373", "#F5EFE6"],
        "fonts": {"headline_font": "Montserrat Bold", "body_font": "Playfair Display"},
        "background_layers": "image fills bottom 60%; cream panel behind top 40%",
    },
    "direct_action_tip": ["Open Magic Media and paste the prompt.", "Add a heading text box."],
}


def _patch_stages(monkeypatch, generate_fn, review_fn):
    monkeypatch.setattr(orchestrator, "build_brief", lambda concept, **kw: BRIEF)
    monkeypatch.setattr(orchestrator, "generate_prompt", generate_fn)
    monkeypatch.setattr(orchestrator, "review_prompt", review_fn)


def test_pipeline_passes_on_first_attempt(monkeypatch):
    _patch_stages(
        monkeypatch,
        lambda brief, concept, feedback=None, **kw: CARD,
        lambda card, **kw: ReviewResult(score=9.0, passed=True, feedback=""),
    )

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

    _patch_stages(monkeypatch, lambda brief, concept, feedback=None, **kw: CARD, fake_review)

    result = orchestrator.run_pipeline("Grand Opening Cafe", max_attempts=3)

    assert result.approved is True
    assert result.attempts == 2
    assert calls["n"] == 2


def test_pipeline_exhausts_attempts_returns_best_effort(monkeypatch):
    _patch_stages(
        monkeypatch,
        lambda brief, concept, feedback=None, **kw: CARD,
        lambda card, **kw: ReviewResult(score=6.0, passed=False, feedback="Too generic."),
    )

    result = orchestrator.run_pipeline("Grand Opening Cafe", max_attempts=2)

    assert result.approved is False
    assert result.attempts == 2
    assert len(result.history) == 2


def test_pipeline_retries_after_generator_validation_failure(monkeypatch):
    calls = {"n": 0}

    def fake_generate(brief, concept, feedback=None, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PromptValidationError("Card contains banned conversational language ('here is').")
        return CARD

    _patch_stages(
        monkeypatch, fake_generate, lambda card, **kw: ReviewResult(score=9.0, passed=True, feedback="")
    )

    result = orchestrator.run_pipeline("Grand Opening Cafe", max_attempts=3)

    assert result.approved is True
    assert result.attempts == 2  # first attempt failed validation, second passed
    assert result.history[0]["card"] is None
    assert "banned conversational language" in result.history[0]["feedback"]


def test_pipeline_raises_pipeline_error_when_generator_never_produces_valid_card(monkeypatch):
    def always_fails(brief, concept, feedback=None, **kw):
        raise PromptValidationError("Card contains banned conversational language ('would you like').")

    monkeypatch.setattr(orchestrator, "build_brief", lambda concept, **kw: BRIEF)
    monkeypatch.setattr(orchestrator, "generate_prompt", always_fails)
    monkeypatch.setattr(
        orchestrator, "review_prompt", lambda card, **kw: ReviewResult(score=9.0, passed=True, feedback="")
    )

    with pytest.raises(PipelineError):
        orchestrator.run_pipeline("Grand Opening Cafe", max_attempts=2)


def test_pipeline_resolves_brand_slug_and_threads_it_to_every_stage(monkeypatch):
    expected_brand = load_brand("example-cafe")
    captured = {}

    def fake_build_brief(concept, *, brand=None, **kw):
        captured["architect_brand"] = brand
        return BRIEF

    def fake_generate(brief, concept, *, brand=None, feedback=None, **kw):
        captured["generator_brand"] = brand
        return CARD

    def fake_review(card, *, brand=None, **kw):
        captured["reviewer_brand"] = brand
        return ReviewResult(score=9.0, passed=True, feedback="")

    monkeypatch.setattr(orchestrator, "build_brief", fake_build_brief)
    monkeypatch.setattr(orchestrator, "generate_prompt", fake_generate)
    monkeypatch.setattr(orchestrator, "review_prompt", fake_review)

    orchestrator.run_pipeline("Grand Opening Cafe", brand="example-cafe")

    assert captured["architect_brand"] == expected_brand
    assert captured["generator_brand"] == expected_brand
    assert captured["reviewer_brand"] == expected_brand


def test_pipeline_unknown_brand_raises_before_any_stage_runs(monkeypatch):
    def must_not_be_called(*args, **kwargs):
        raise AssertionError("build_brief should never run for an unknown brand")

    monkeypatch.setattr(orchestrator, "build_brief", must_not_be_called)

    with pytest.raises(BrandNotFoundError):
        orchestrator.run_pipeline("Grand Opening Cafe", brand="does-not-exist")


def test_pipeline_without_brand_passes_none_through(monkeypatch):
    captured = {}

    def fake_build_brief(concept, *, brand=None, **kw):
        captured["brand"] = brand
        return BRIEF

    monkeypatch.setattr(orchestrator, "build_brief", fake_build_brief)
    monkeypatch.setattr(orchestrator, "generate_prompt", lambda brief, concept, feedback=None, **kw: CARD)
    monkeypatch.setattr(
        orchestrator, "review_prompt", lambda card, **kw: ReviewResult(score=9.0, passed=True, feedback="")
    )

    orchestrator.run_pipeline("Grand Opening Cafe")

    assert captured["brand"] is None


def test_pipeline_resolves_style_slug_and_threads_it_to_architect_and_generator(monkeypatch):
    expected_style = load_style("neo-grunge-streetwear")
    captured = {}

    def fake_build_brief(concept, *, brand=None, style=None, **kw):
        captured["architect_style"] = style
        return BRIEF

    def fake_generate(brief, concept, *, brand=None, style=None, feedback=None, **kw):
        captured["generator_style"] = style
        return CARD

    monkeypatch.setattr(orchestrator, "build_brief", fake_build_brief)
    monkeypatch.setattr(orchestrator, "generate_prompt", fake_generate)
    monkeypatch.setattr(
        orchestrator, "review_prompt", lambda card, **kw: ReviewResult(score=9.0, passed=True, feedback="")
    )

    orchestrator.run_pipeline("Grand Opening Cafe", style="neo-grunge-streetwear")

    assert captured["architect_style"] == expected_style
    assert captured["generator_style"] == expected_style


def test_pipeline_unknown_style_raises_before_any_stage_runs(monkeypatch):
    def must_not_be_called(*args, **kwargs):
        raise AssertionError("build_brief should never run for an unknown style")

    monkeypatch.setattr(orchestrator, "build_brief", must_not_be_called)

    with pytest.raises(StyleNotFoundError):
        orchestrator.run_pipeline("Grand Opening Cafe", style="does-not-exist")
