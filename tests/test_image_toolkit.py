from __future__ import annotations

import io
import json
import zipfile

from PIL import Image

from src.image_toolkit import optimize_under_limit, tile_bundle, upscale_image


def _sample_png(width: int = 320, height: int = 180) -> bytes:
    image = Image.new("RGB", (width, height), (220, 190, 140))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_optimizer_preserves_dimensions_and_hits_target():
    source = _sample_png()
    output, extension, manifest = optimize_under_limit(source, target_mb=1)
    assert extension in {"png", "webp", "jpeg"}
    assert len(output) <= 1024 * 1024
    assert manifest["width"] == 320
    assert manifest["height"] == 180


def test_upscale_doubles_dimensions():
    output, manifest = upscale_image(_sample_png(), factor=2)
    image = Image.open(io.BytesIO(output))
    assert image.size == (640, 360)
    assert manifest["factor"] == 2


def test_tile_bundle_contains_manifest_and_all_tiles():
    archive, manifest = tile_bundle(_sample_png(), columns=2, rows=2, overlap_px=8)
    assert len(manifest["tiles"]) == 4
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        names = zf.namelist()
        assert "placement_manifest.json" in names
        assert len([name for name in names if name.startswith("tile_")]) == 4
        stored = json.loads(zf.read("placement_manifest.json"))
        assert stored["canvas"] == {"width": 320, "height": 180}
