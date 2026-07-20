from types import SimpleNamespace

from fastapi.testclient import TestClient

import api

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

client = TestClient(api.app)


def _fake_result(**over):
    base = {"card": CARD, "review": SimpleNamespace(score=9.0, feedback=""), "attempts": 1, "approved": True}
    base.update(over)
    return SimpleNamespace(**base)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_chat_returns_card(monkeypatch):
    monkeypatch.setattr(api, "run_pipeline", lambda message, max_attempts=3: _fake_result())

    resp = client.post("/api/chat", json={"message": "Kafe acilisi icin Instagram gonderisi"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["approved"] is True
    assert body["score"] == 9.0
    assert body["card"]["target_tool"] == "Canva Magic Media"


def test_chat_rejects_empty_message():
    resp = client.post("/api/chat", json={"message": ""})
    assert resp.status_code == 422


def test_chat_surfaces_pipeline_error_as_502(monkeypatch):
    def boom(message, max_attempts=3):
        raise RuntimeError("deepseek down")

    monkeypatch.setattr(api, "run_pipeline", boom)
    resp = client.post("/api/chat", json={"message": "a poster"})
    assert resp.status_code == 502
    assert "deepseek down" in resp.json()["detail"]


def test_chat_surfaces_validation_exhaustion_as_502(monkeypatch):
    from src.orchestrator import PipelineError

    def boom(message, max_attempts=3):
        raise PipelineError("Generator failed to produce a valid card in 3 attempts.")

    monkeypatch.setattr(api, "run_pipeline", boom)
    resp = client.post("/api/chat", json={"message": "a poster"})
    assert resp.status_code == 502
    assert "Generator failed" in resp.json()["detail"]
