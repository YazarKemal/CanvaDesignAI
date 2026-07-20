from types import SimpleNamespace

from fastapi.testclient import TestClient

import api

CARD = {
    "concept": "Grand Opening Cafe",
    "magic_media_prompt": "A minimalist flat vector espresso cup, terracotta palette, negative space at top.",
    "negative_prompt": "embedded text, watermark",
    "aspect_ratio": "1:1 (1080x1080)",
    "target_tool": "Canva Magic Media",
    "text_zone": "top",
    "layer_typography_architecture": {
        "headline": "Grand Opening",
        "subtext": "Freshly roasted, every morning.",
        "color_palette": ["#4A2E1B", "#D4A373", "#F5EFE6"],
        "fonts": {"headline_font": "Montserrat Bold", "body_font": "Playfair Display"},
        "background_layers": "image fills bottom 60%; cream panel behind top 40%",
    },
    "direct_action_tip": ["Open Magic Media and paste the prompt.", "Add a heading text box."],
}

client = TestClient(api.app)


def _fake_result(**over):
    base = {"card": CARD, "review": SimpleNamespace(score=9.0, feedback=""), "attempts": 1, "approved": True}
    base.update(over)
    return SimpleNamespace(**base)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_chat_returns_card(monkeypatch):
    monkeypatch.setattr(api, "run_pipeline", lambda message, brand=None, max_attempts=3: _fake_result())

    resp = client.post("/api/chat", json={"message": "Kafe acilisi icin Instagram gonderisi"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["approved"] is True
    assert body["score"] == 9.0
    assert body["card"]["target_tool"] == "Canva Magic Media"
    assert body["paste_text"].startswith("Instruction:")
    assert CARD["magic_media_prompt"] in body["paste_text"]
    assert body["text_zone"] == "top"
    assert body["contrast_ratio"] > 4.5


def test_chat_rejects_empty_message():
    resp = client.post("/api/chat", json={"message": ""})
    assert resp.status_code == 422


def test_chat_surfaces_pipeline_error_as_502(monkeypatch):
    def boom(message, brand=None, max_attempts=3):
        raise RuntimeError("deepseek down")

    monkeypatch.setattr(api, "run_pipeline", boom)
    resp = client.post("/api/chat", json={"message": "a poster"})
    assert resp.status_code == 502
    assert "deepseek down" in resp.json()["detail"]


def test_chat_surfaces_validation_exhaustion_as_502(monkeypatch):
    from src.orchestrator import PipelineError

    def boom(message, brand=None, max_attempts=3):
        raise PipelineError("Generator failed to produce a valid card in 3 attempts.")

    monkeypatch.setattr(api, "run_pipeline", boom)
    resp = client.post("/api/chat", json={"message": "a poster"})
    assert resp.status_code == 502
    assert "Generator failed" in resp.json()["detail"]


def test_chat_unknown_brand_returns_404(monkeypatch):
    from src.brand_profiles import BrandNotFoundError

    def boom(message, brand=None, max_attempts=3):
        raise BrandNotFoundError(f"No brand profile named '{brand}'.")

    monkeypatch.setattr(api, "run_pipeline", boom)
    resp = client.post("/api/chat", json={"message": "a poster", "brand": "does-not-exist"})
    assert resp.status_code == 404


def test_get_brands_lists_example_brand():
    resp = client.get("/api/brands")
    assert resp.status_code == 200
    slugs = [b["slug"] for b in resp.json()["brands"]]
    assert "example-cafe" in slugs


def test_adapt_returns_variants(monkeypatch):
    def fake_set(base_card, formats, *, brand=None, **kw):
        return {fmt: {**base_card, "aspect_ratio": fmt} for fmt in formats}

    monkeypatch.setattr(api, "generate_omni_channel_set", fake_set)

    resp = client.post("/api/adapt", json={"card": CARD, "formats": ["instagram_story", "banner"]})

    assert resp.status_code == 200
    variants = resp.json()["variants"]
    assert set(variants) == {"instagram_story", "banner"}


def test_adapt_unknown_format_returns_400(monkeypatch):
    from src.omni_channel import UnknownFormatError

    def boom(base_card, formats, *, brand=None, **kw):
        raise UnknownFormatError("Unknown target format 'nope'.")

    monkeypatch.setattr(api, "generate_omni_channel_set", boom)
    resp = client.post("/api/adapt", json={"card": CARD, "formats": ["nope"]})
    assert resp.status_code == 400


def test_adapt_unknown_brand_returns_404():
    resp = client.post(
        "/api/adapt", json={"card": CARD, "formats": ["banner"], "brand": "does-not-exist"}
    )
    assert resp.status_code == 404


def test_adapt_validation_failure_returns_502(monkeypatch):
    from src.schema import PromptValidationError

    def boom(base_card, formats, *, brand=None, **kw):
        raise PromptValidationError("Adaptation never passed validation.")

    monkeypatch.setattr(api, "generate_omni_channel_set", boom)
    resp = client.post("/api/adapt", json={"card": CARD, "formats": ["banner"]})
    assert resp.status_code == 502
