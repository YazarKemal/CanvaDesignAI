"""Server-side palette extraction from template images.

The vision model cannot sample pixel colours — it rounds to known named
colours.  This module extracts the dominant palette from the uploaded image
bytes so the card always carries real, pixel-accurate hex codes.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image


def extract_palette(image_bytes: bytes, n: int = 5) -> list[str]:
    """Return the *n* dominant colours of *image_bytes* as sorted hex strings.

    The image is downsized (max 200 px longest edge), converted to RGB, then
    quantised to *n* colours via Pillow's ``quantize()`` (median-cut).  Colours
    are returned in descending order of pixel coverage.
    """
    img = Image.open(BytesIO(image_bytes))
    img = img.convert("RGB")

    # Downsize so quantize runs on a uniform small canvas.
    img.thumbnail((200, 200), Image.LANCZOS)

    # Quantize to exactly n colours, then count pixel frequencies.
    quantized = img.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    raw_palette = quantized.getpalette() or []
    # getpalette() may return fewer entries than n*3 for images with
    # very few distinct colours — clamp to what is actually available.
    available = len(raw_palette) // 3
    actual_n = min(n, available)
    if actual_n == 0:
        return []
    palette = raw_palette[: actual_n * 3]
    # Count occurrences of each palette index.
    counts = quantized.histogram()[:actual_n]

    # Build (count, hex) pairs, sort descending by count.
    colours: list[tuple[int, str]] = []
    for i in range(actual_n):
        r, g, b = palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2]
        hex_code = f"#{r:02X}{g:02X}{b:02X}"
        colours.append((counts[i], hex_code))

    colours.sort(key=lambda c: c[0], reverse=True)
    return [hex_code for _count, hex_code in colours if _count > 0]
