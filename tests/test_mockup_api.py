"""Offline API tests for mockup_api.py."""

from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

import mockup_api


client = TestClient(mockup_api.app)


def _png_bytes() -> bytes:
    image = Image.new("RGB", (300, 450), (30, 40, 50))
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "cavdesign-mockup-director"


def test_mockup_types_returns_six_types():
    response = client.get("/api/mockup/types")
    assert response.status_code == 200
    assert len(response.json()["types"]) == 6


def test_analyze_passes_upload_and_form_context(monkeypatch):
    captured = {}

    def fake_generate(image_bytes, mime_type, **kwargs):
        captured["bytes"] = image_bytes
        captured["mime"] = mime_type
        captured.update(kwargs)
        return {"ok": True, "mockups": []}

    monkeypatch.setattr(mockup_api, "generate_mockup_set", fake_generate)

    response = client.post(
        "/api/mockup/analyze",
        files={"file": ("poster.png", _png_bytes(), "image/png")},
        data={
            "marketplace": "Etsy",
            "product_type_hint": "film poster",
            "audience_hint": "cinephiles",
            "creative_direction": "dark editorial",
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured["mime"] == "image/png"
    assert captured["marketplace"] == "Etsy"
    assert captured["product_type_hint"] == "film poster"
    assert captured["audience_hint"] == "cinephiles"
    assert captured["creative_direction"] == "dark editorial"
    assert len(captured["bytes"]) > 0


def test_analyze_rejects_unsupported_mime_type():
    response = client.post(
        "/api/mockup/analyze",
        files={"file": ("poster.gif", b"GIF89a", "image/gif")},
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_analyze_rejects_empty_file():
    response = client.post(
        "/api/mockup/analyze",
        files={"file": ("poster.png", b"", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file is empty."
