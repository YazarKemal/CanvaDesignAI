"""Publishes an approved design draft (see src/schema.py) into a real Canva
design: generate the main visual, upload it as an asset, and create a
design from it.
"""

from __future__ import annotations

from typing import Any

from src.canva_client import CanvaClient
from src.image_provider import OpenAIImageProvider

DEFAULT_CANVA_DESIGN_TYPE = "poster"


def publish_design_to_canva(
    design: dict[str, Any],
    *,
    canva_client: CanvaClient,
    image_provider: OpenAIImageProvider,
    design_type: str = DEFAULT_CANVA_DESIGN_TYPE,
) -> dict[str, str]:
    """Turn a structured design draft into a real Canva design.

    Returns {"asset_id": ..., "design_id": ..., "edit_url": ..., "view_url": ...}.
    """
    prompt = design["image_prompts"]["main_visual"]
    image_bytes = image_provider.generate_image(prompt)

    asset_id = canva_client.upload_asset(image_bytes, name=design["theme"])
    created = canva_client.create_design(design_type=design_type, asset_id=asset_id, title=design["theme"])

    return {
        "asset_id": asset_id,
        "design_id": created["id"],
        "edit_url": created["edit_url"],
        "view_url": created["view_url"],
    }
