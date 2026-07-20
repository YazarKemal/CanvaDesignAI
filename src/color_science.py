"""Deterministic color math backing the Art Director constitution's color
theory rules — WCAG contrast and hue-clash checks computed from real HEX
values, not just described in a prompt and trusted to the LLM.
"""

from __future__ import annotations

import colorsys


class InvalidHexColorError(ValueError):
    pass


def _parse_hex(hex_color: str) -> tuple[float, float, float]:
    """Parse '#RRGGBB' into (r, g, b) floats in [0, 1]."""
    text = hex_color.strip().lstrip("#")
    if len(text) != 6:
        raise InvalidHexColorError(f"Expected a 6-digit HEX color, got {hex_color!r}")
    try:
        r = int(text[0:2], 16) / 255.0
        g = int(text[2:4], 16) / 255.0
        b = int(text[4:6], 16) / 255.0
    except ValueError as exc:
        raise InvalidHexColorError(f"Expected a 6-digit HEX color, got {hex_color!r}") from exc
    return r, g, b


def relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance of a HEX color (0 = black, 1 = white)."""
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _parse_hex(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """WCAG contrast ratio between two HEX colors, in [1, 21]."""
    l1 = relative_luminance(hex_a)
    l2 = relative_luminance(hex_b)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def hue_saturation(hex_color: str) -> tuple[float, float]:
    """Return (hue_degrees [0,360), saturation [0,1]) for a HEX color."""
    r, g, b = _parse_hex(hex_color)
    h, _l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360.0, s


def hue_distance(hex_a: str, hex_b: str) -> float:
    """Shortest distance between two hues on the 360-degree color wheel."""
    ha, _ = hue_saturation(hex_a)
    hb, _ = hue_saturation(hex_b)
    diff = abs(ha - hb) % 360.0
    return min(diff, 360.0 - diff)


def is_clashing_pair(hex_a: str, hex_b: str, *, saturation_threshold: float = 0.6, hue_window: float = 40.0) -> bool:
    """True if both colors are highly saturated AND sit in the narrow hue
    band that reads as an optical clash (vibrating, amateur-looking) rather
    than a deliberate complementary/triadic scheme (which sits further
    apart on the wheel)."""
    _, sa = hue_saturation(hex_a)
    _, sb = hue_saturation(hex_b)
    if sa < saturation_threshold or sb < saturation_threshold:
        return False
    distance = hue_distance(hex_a, hex_b)
    # Clashes cluster near-adjacent (too similar, muddy) hues; true
    # complementary pairs (~180 degrees apart) are a deliberate scheme, not
    # a clash, so only flag the near-adjacent band.
    return distance <= hue_window


def best_contrast_pair(colors: list[str]) -> tuple[str, str, float]:
    """Given a palette, return the (color_a, color_b, ratio) pair with the
    highest contrast ratio — simulating the best available text/background
    combination within that palette."""
    if len(colors) < 2:
        raise ValueError("Need at least 2 colors to compute a contrast pair.")

    best: tuple[str, str, float] | None = None
    for i, a in enumerate(colors):
        for b in colors[i + 1 :]:
            ratio = contrast_ratio(a, b)
            if best is None or ratio > best[2]:
                best = (a, b, ratio)
    assert best is not None
    return best
