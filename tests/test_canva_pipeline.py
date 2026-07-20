from src.canva_pipeline import publish_design_to_canva

DESIGN = {
    "theme": "Modern Cafe",
    "color_palette": ["#4A2E1B", "#F5EFE6", "#D4A373"],
    "typography": {"headline": "Montserrat Bold", "body_text": "Join us!"},
    "image_prompts": {"main_visual": "A latte with micro-foam art on a wooden table."},
    "layout_instructions": "Top 40% text, bottom 60% visual.",
}


class _FakeImageProvider:
    def __init__(self):
        self.captured_prompt = None

    def generate_image(self, prompt, **kwargs):
        self.captured_prompt = prompt
        return b"fake-image-bytes"


class _FakeCanvaClient:
    def __init__(self):
        self.uploaded = None
        self.created_kwargs = None

    def upload_asset(self, image_bytes, *, name, **kwargs):
        self.uploaded = (image_bytes, name)
        return "asset-123"

    def create_design(self, *, design_type, asset_id=None, title=None):
        self.created_kwargs = {"design_type": design_type, "asset_id": asset_id, "title": title}
        return {"id": "design-123", "edit_url": "https://canva.com/edit/design-123", "view_url": "https://canva.com/view/design-123"}


def test_publish_design_to_canva_wires_prompt_through_upload_and_create():
    image_provider = _FakeImageProvider()
    canva_client = _FakeCanvaClient()

    result = publish_design_to_canva(DESIGN, canva_client=canva_client, image_provider=image_provider)

    assert image_provider.captured_prompt == DESIGN["image_prompts"]["main_visual"]
    assert canva_client.uploaded == (b"fake-image-bytes", "Modern Cafe")
    assert canva_client.created_kwargs == {"design_type": "poster", "asset_id": "asset-123", "title": "Modern Cafe"}
    assert result == {
        "asset_id": "asset-123",
        "design_id": "design-123",
        "edit_url": "https://canva.com/edit/design-123",
        "view_url": "https://canva.com/view/design-123",
    }


def test_publish_design_to_canva_uses_custom_design_type():
    image_provider = _FakeImageProvider()
    canva_client = _FakeCanvaClient()

    publish_design_to_canva(DESIGN, canva_client=canva_client, image_provider=image_provider, design_type="flyer")

    assert canva_client.created_kwargs["design_type"] == "flyer"
