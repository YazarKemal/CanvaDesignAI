"""Memory-conscious image preparation utilities for Canva workflows.

The engine keeps the master image at full resolution while producing:
- a Canva Magic Layers compatible file below a target size,
- high-quality 2x / 4x upscaled exports,
- overlapping tiles for very large compositions,
- a ZIP bundle with a placement manifest.

True semantic layer extraction is intentionally exposed as a future segmentation
provider; this module never claims that rectangular tiles are object layers.
"""

from __future__ import annotations

import io
import json
import math
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageFilter, ImageOps

OutputMode = Literal["optimize", "upscale", "tiles"]


class ImageToolkitError(ValueError):
    """Raised for invalid image-toolkit requests."""


@dataclass(frozen=True)
class ImageInfo:
    width: int
    height: int
    mode: str
    source_bytes: int


def _open_image(image_bytes: bytes) -> Image.Image:
    if not image_bytes:
        raise ImageToolkitError("Uploaded image is empty.")
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.load()
    except Exception as exc:
        raise ImageToolkitError(f"Could not decode image: {exc}") from exc

    # Respect phone / camera orientation and normalize for predictable exports.
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    return image


def inspect_image(image_bytes: bytes) -> ImageInfo:
    image = _open_image(image_bytes)
    return ImageInfo(image.width, image.height, image.mode, len(image_bytes))


def _flatten_for_jpeg(image: Image.Image, matte: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    if image.mode == "RGB":
        return image
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, (*matte, 255))
    background.alpha_composite(rgba)
    return background.convert("RGB")


def optimize_under_limit(
    image_bytes: bytes,
    *,
    target_mb: float = 49.0,
    preferred_format: Literal["auto", "jpeg", "webp", "png"] = "auto",
) -> tuple[bytes, str, dict]:
    """Keep pixel dimensions unchanged while fitting under ``target_mb``.

    PNG is attempted first for graphic artwork. If it misses the limit, the
    function binary-searches high-quality WebP or JPEG encodes. No resampling is
    performed in this mode.
    """
    if not 1 <= target_mb <= 200:
        raise ImageToolkitError("target_mb must be between 1 and 200.")

    image = _open_image(image_bytes)
    target = int(target_mb * 1024 * 1024)

    candidates: list[tuple[bytes, str, int]] = []

    if preferred_format in ("auto", "png"):
        buf = io.BytesIO()
        image.save(buf, format="PNG", optimize=True, compress_level=9)
        data = buf.getvalue()
        candidates.append((data, "png", 100))
        if len(data) <= target:
            return data, "png", _manifest(image, image_bytes, data, "optimize", quality=100)
        if preferred_format == "png":
            raise ImageToolkitError(
                "Lossless PNG cannot reach the requested size without reducing dimensions. "
                "Use auto, WebP, or JPEG."
            )

    formats = [preferred_format] if preferred_format != "auto" else ["webp", "jpeg"]
    for fmt in formats:
        encoded = _best_quality_under_target(image, fmt, target)
        if encoded is not None:
            data, quality = encoded
            candidates.append((data, fmt, quality))

    fitting = [item for item in candidates if len(item[0]) <= target]
    if not fitting:
        raise ImageToolkitError(
            "The image cannot fit below the target at the minimum safe quality. "
            "Use tile mode or permit a larger file."
        )

    # Highest quality wins; WebP wins ties because it typically preserves line art better.
    data, fmt, quality = max(fitting, key=lambda item: (item[2], item[1] == "webp"))
    return data, fmt, _manifest(image, image_bytes, data, "optimize", quality=quality)


def _best_quality_under_target(
    image: Image.Image,
    fmt: str,
    target: int,
    *,
    min_quality: int = 82,
    max_quality: int = 100,
) -> tuple[bytes, int] | None:
    source = _flatten_for_jpeg(image) if fmt == "jpeg" else image
    best: tuple[bytes, int] | None = None
    lo, hi = min_quality, max_quality

    while lo <= hi:
        quality = (lo + hi) // 2
        buf = io.BytesIO()
        kwargs = {"quality": quality, "method": 6}
        if fmt == "jpeg":
            kwargs = {"quality": quality, "optimize": True, "progressive": True, "subsampling": 0}
        source.save(buf, format=fmt.upper(), **kwargs)
        data = buf.getvalue()
        if len(data) <= target:
            best = (data, quality)
            lo = quality + 1
        else:
            hi = quality - 1
    return best


def upscale_image(image_bytes: bytes, *, factor: int = 2, sharpen: bool = True) -> tuple[bytes, dict]:
    """High-quality deterministic upscale.

    This is a reconstruction-safe Lanczos upscale, not generative AI. It is ideal
    for line art and avoids inventing details. A Real-ESRGAN provider can be added
    later behind the same endpoint for photographic assets.
    """
    if factor not in (2, 4):
        raise ImageToolkitError("factor must be 2 or 4.")
    image = _open_image(image_bytes)
    output = image.resize((image.width * factor, image.height * factor), Image.Resampling.LANCZOS)
    if sharpen:
        output = output.filter(ImageFilter.UnsharpMask(radius=1.2, percent=110, threshold=3))
    buf = io.BytesIO()
    output.save(buf, format="PNG", optimize=True, compress_level=7)
    data = buf.getvalue()
    return data, _manifest(output, image_bytes, data, "upscale", factor=factor)


def tile_bundle(
    image_bytes: bytes,
    *,
    columns: int = 2,
    rows: int = 2,
    overlap_px: int = 32,
    output_format: Literal["png", "webp"] = "png",
) -> tuple[bytes, dict]:
    """Split a master image into overlapping rectangular tiles.

    Tiles preserve every source pixel and include exact placement metadata. They
    are transport pieces, not semantic object layers.
    """
    if not 1 <= columns <= 8 or not 1 <= rows <= 8:
        raise ImageToolkitError("rows and columns must be between 1 and 8.")
    if not 0 <= overlap_px <= 512:
        raise ImageToolkitError("overlap_px must be between 0 and 512.")

    image = _open_image(image_bytes)
    tile_w = math.ceil(image.width / columns)
    tile_h = math.ceil(image.height / rows)
    manifest = {
        "kind": "canva_tiles",
        "canvas": {"width": image.width, "height": image.height},
        "grid": {"columns": columns, "rows": rows, "overlap_px": overlap_px},
        "tiles": [],
        "note": "These are rectangular transport tiles, not semantic object layers.",
    }

    archive_buf = io.BytesIO()
    with zipfile.ZipFile(archive_buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        index = 0
        for row in range(rows):
            for col in range(columns):
                x0 = max(0, col * tile_w - (overlap_px if col else 0))
                y0 = max(0, row * tile_h - (overlap_px if row else 0))
                x1 = min(image.width, (col + 1) * tile_w + (overlap_px if col < columns - 1 else 0))
                y1 = min(image.height, (row + 1) * tile_h + (overlap_px if row < rows - 1 else 0))
                tile = image.crop((x0, y0, x1, y1))
                index += 1
                name = f"tile_{index:02d}_r{row + 1}_c{col + 1}.{output_format}"
                tile_buf = io.BytesIO()
                if output_format == "png":
                    tile.save(tile_buf, format="PNG", optimize=True, compress_level=8)
                else:
                    tile.save(tile_buf, format="WEBP", quality=98, method=6)
                archive.writestr(name, tile_buf.getvalue())
                manifest["tiles"].append(
                    {
                        "file": name,
                        "x": x0,
                        "y": y0,
                        "width": x1 - x0,
                        "height": y1 - y0,
                    }
                )
        archive.writestr("placement_manifest.json", json.dumps(manifest, indent=2))
        archive.writestr(
            "CANVA_README.txt",
            "Create a Canva canvas matching placement_manifest.json. "
            "Upload every tile, keep its proportions, and align using the x/y order. "
            "The overlap prevents hairline seams.\n",
        )
    return archive_buf.getvalue(), manifest


def _manifest(
    image: Image.Image,
    source_bytes: bytes,
    output_bytes: bytes,
    operation: str,
    **extra: object,
) -> dict:
    return {
        "operation": operation,
        "width": image.width,
        "height": image.height,
        "mode": image.mode,
        "source_bytes": len(source_bytes),
        "output_bytes": len(output_bytes),
        **extra,
    }
