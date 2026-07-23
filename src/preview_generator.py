"""HTML/SVG wireframe preview generator for Canva automation cards.

Renders a self-contained HTML document that visualises a card's layout
as a box-model wireframe: the canvas shape, text_zone position, headline
and subtext placement, colour-palette swatches, and typography metadata.
Useful for quick sanity-checking a generated card before pasting it into
Canva — the wireframe makes it obvious when the text zone doesn't match
the image description or the palette lacks a legible contrast anchor.

Public API
----------
``generate_wireframe(card) -> str``
    Return a complete, standalone HTML document string.
"""

from __future__ import annotations

import re
from typing import Any

from src.color_science import best_contrast_pair

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MAX_CANVAS_WIDTH = 640  # px — SVG renders at this display width
_TEXT_ZONE_FRACTION = 0.32  # fraction of canvas occupied by the text zone


def _resolve_layer(card: dict[str, Any]) -> dict[str, Any]:
    """Return the typography-layer dict whether the card uses the new hybrid
    format (native_typography) or the legacy format (layer_typography_architecture)."""
    native = card.get("native_typography", {})
    legacy = card.get("layer_typography_architecture", {})
    # Merge: native wins, legacy is fallback for each key.
    return {
        "headline": native.get("headline", legacy.get("headline", "")),
        "subtext": native.get("subtext", legacy.get("subtext", "")),
        "color_palette": native.get("color_palette", legacy.get("color_palette", [])),
        "fonts": native.get("fonts", legacy.get("fonts", {})),
        "alignment_zone": native.get("alignment_zone", legacy.get("background_layers", "")),
    }


def _resolve_style_name(card: dict[str, Any]) -> str | None:
    """Return the layout/magic-media style name from either format."""
    raster = card.get("raster_background", {})
    if "layout_style" in raster:
        return raster["layout_style"]
    if "magic_media_style" in raster:
        return raster["magic_media_style"]
    legacy = card.get("layer_typography_architecture", {})
    return legacy.get("magic_media_style")


def _parse_pixel_dims(aspect_ratio: str) -> tuple[int, int]:
    """Extract (width, height) in pixels from an aspect-ratio string.

    Handles every format the knowledge base emits:
    ``"1080x1080 (1:1)"``, ``"2480x3508 (3:4 aspect)"``, etc.
    """
    m = re.search(r"(\d+)\s*[x×]\s*(\d+)", aspect_ratio)
    if m:
        return int(m.group(1)), int(m.group(2))
    # Fallback: try a plain ratio like "16:9"
    m = re.search(r"(\d+)\s*:\s*(\d+)", aspect_ratio)
    if m:
        w_ratio, h_ratio = int(m.group(1)), int(m.group(2))
        return (w_ratio * 100, h_ratio * 100)  # arbitrary scale
    return (1080, 1080)  # safest default


def _svg_viewbox(w: int, h: int) -> str:
    """Return a ``viewBox`` string scaled to *_MAX_CANVAS_WIDTH*."""
    scale = _MAX_CANVAS_WIDTH / w
    return f"0 0 {w} {h}"


def _text_zone_rect(w: int, h: int, zone: str) -> tuple[int, int, int, int]:
    """Return (x, y, width, height) for the text-zone highlight rectangle."""
    if zone == "top":
        return (0, 0, w, int(h * _TEXT_ZONE_FRACTION))
    elif zone == "bottom":
        th = int(h * _TEXT_ZONE_FRACTION)
        return (0, h - th, w, th)
    elif zone == "left":
        tw = int(w * _TEXT_ZONE_FRACTION)
        return (0, 0, tw, h)
    elif zone == "right":
        tw = int(w * _TEXT_ZONE_FRACTION)
        return (w - tw, 0, tw, h)
    else:  # center — floating inset box
        tw = int(w * 0.55)
        th = int(h * 0.35)
        return ((w - tw) // 2, (h - th) // 2, tw, th)


def _text_position(
    w: int, h: int, zone: str
) -> tuple[float, float, float, float, str, str]:
    """Return (headline_x, headline_y, subtext_x, subtext_y, anchor, sub_anchor)
    for placing headline/subtext SVG <text> elements inside the text zone.

    Coordinates are absolute pixel positions within the SVG viewBox.
    """
    margin = 0.06  # margin from zone edge in fraction of canvas dimension
    if zone == "top":
        hx = w / 2
        hy = int(h * _TEXT_ZONE_FRACTION * 0.38)
        sx = w / 2
        sy = int(h * _TEXT_ZONE_FRACTION * 0.68)
        return (hx, hy, sx, sy, "middle", "middle")
    elif zone == "bottom":
        th = int(h * _TEXT_ZONE_FRACTION)
        hx = w / 2
        hy = (h - th) + int(th * 0.32)
        sx = w / 2
        sy = (h - th) + int(th * 0.65)
        return (hx, hy, sx, sy, "middle", "middle")
    elif zone == "left":
        tw = int(w * _TEXT_ZONE_FRACTION)
        hx = tw / 2
        hy = h * 0.32
        sx = tw / 2
        sy = h * 0.58
        return (hx, hy, sx, sy, "middle", "middle")
    elif zone == "right":
        tw = int(w * _TEXT_ZONE_FRACTION)
        hx = w - tw + tw / 2
        hy = h * 0.32
        sx = w - tw + tw / 2
        sy = h * 0.58
        return (hx, hy, sx, sy, "middle", "middle")
    else:  # center
        hx = w / 2
        hy = h * 0.40
        sx = w / 2
        sy = h * 0.55
        return (hx, hy, sx, sy, "middle", "middle")


# ---------------------------------------------------------------------------
# Sub-renderers (each returns a plain str of HTML / SVG content)
# ---------------------------------------------------------------------------

_CSS = """\
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0d0d0d;
    color: #e0e0e0;
    display: flex; justify-content: center;
    padding: 32px 16px 64px;
  }
  .wireframe-card {
    max-width: 720px; width: 100%;
  }
  .wireframe-card h1 {
    font-size: 1.25rem; font-weight: 600; color: #ffffff;
    margin-bottom: 4px;
  }
  .meta-row {
    display: flex; flex-wrap: wrap; gap: 8px 20px;
    font-size: 0.78rem; color: #888; margin-bottom: 20px;
  }
  .meta-row span { white-space: nowrap; }
  .meta-row strong { color: #ccc; }

  /* ---- SVG canvas ---- */
  .canvas-wrap {
    background: #1a1a1a; border: 1px solid #333; border-radius: 10px;
    overflow: hidden; margin-bottom: 20px;
  }
  .canvas-wrap svg { display: block; width: 100%; height: auto; }

  /* ---- Palette ---- */
  .section-title {
    font-size: 0.85rem; font-weight: 600; color: #aaa;
    text-transform: uppercase; letter-spacing: 0.06em;
    margin-bottom: 10px;
  }
  .swatches {
    display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 18px;
  }
  .swatch {
    display: flex; align-items: center; gap: 8px;
    background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px;
    padding: 6px 12px 6px 8px;
  }
  .swatch-chip {
    width: 28px; height: 28px; border-radius: 5px;
    border: 1px solid rgba(255,255,255,0.08);
  }
  .swatch-hex {
    font-family: "JetBrains Mono", "Fira Code", monospace;
    font-size: 0.78rem; color: #ccc;
  }

  /* ---- Typography ---- */
  .typo-grid {
    display: grid; grid-template-columns: auto 1fr; gap: 6px 16px;
    font-size: 0.82rem; margin-bottom: 20px;
  }
  .typo-label { color: #888; }
  .typo-value { color: #ddd; font-weight: 500; }

  /* ---- Contrast badge ---- */
  .contrast-badge {
    display: inline-block; font-size: 0.72rem; font-weight: 600;
    padding: 3px 10px; border-radius: 99px; margin-left: 8px;
  }
  .contrast-ok  { background: #1a3a1a; color: #6fcf6f; }
  .contrast-bad { background: #3a1a1a; color: #ef6b6b; }

  /* ---- Zone info ---- */
  .zone-tag {
    display: inline-block; font-size: 0.72rem; font-weight: 600;
    background: #222; color: #aaa; padding: 3px 10px;
    border-radius: 99px; margin-right: 6px;
  }
"""


def _render_svg(card: dict[str, Any]) -> str:
    """Return the ``<svg>…</svg>`` wireframe element."""
    layer = _resolve_layer(card)
    zone = card["text_zone"]
    palette = layer["color_palette"]
    headline = layer["headline"]
    subtext = layer["subtext"]
    concept = card.get("concept", "")

    w, h = _parse_pixel_dims(card["aspect_ratio"])
    vb = _svg_viewbox(w, h)
    zx, zy, zw, zh = _text_zone_rect(w, h, zone)
    hx, hy, sx, sy, ha, sa = _text_position(w, h, zone)

    # Pick two palette colours for the text-zone background / text fill so
    # the wireframe suggests what the real contrast will look like.
    bg_hex = palette[0]
    fg_hex = palette[-1] if len(palette) > 1 else "#FFFFFF"
    # Try to use the best-contrast pair for the text-on-zone rendering.
    try:
        _a, _b, ratio = best_contrast_pair(palette)
        bg_hex, fg_hex = _a, _b
    except Exception:
        pass

    # Slightly desaturate / lighten the bg colour for the wireframe fill so
    # it reads as a tinted zone rather than a solid block.
    zone_fill = _desaturate_hex(bg_hex, 0.35)
    zone_stroke = bg_hex
    text_fill = fg_hex

    image_fill = "#151515"
    image_stroke = "#2a2a2a"

    def _font_size(axis: int) -> int:
        """Heuristic: headline ~6% of the short axis, subtext ~3.5%."""
        short = min(w, h)
        return max(14, int(short * 0.06))

    hl_size = _font_size(min(w, h))
    sub_size = max(12, int(hl_size * 0.58))

    return f"""\
<svg viewBox="{vb}" xmlns="http://www.w3.org/2000/svg"
     style="background:#111; font-family: system-ui, sans-serif;">
  <defs>
    <pattern id="img-hatch" patternUnits="userSpaceOnUse"
             width="20" height="20" patternTransform="rotate(45)">
      <line x1="0" y1="0" x2="0" y2="20" stroke="#222" stroke-width="1"/>
    </pattern>
  </defs>

  <!-- Image area -->
  <rect x="0" y="0" width="{w}" height="{h}"
        fill="{image_fill}" stroke="{image_stroke}" stroke-width="2"/>
  <rect x="0" y="0" width="{w}" height="{h}" fill="url(#img-hatch)" opacity="0.6"/>

  <!-- Text-zone highlight -->
  <rect x="{zx}" y="{zy}" width="{zw}" height="{zh}"
        fill="{zone_fill}" stroke="{zone_stroke}" stroke-width="2.5"
        stroke-dasharray="10 5" rx="2" opacity="0.85"/>

  <!-- Headline -->
  <text x="{hx:.0f}" y="{hy:.0f}" text-anchor="{ha}"
        fill="{text_fill}" font-size="{hl_size}" font-weight="700"
        letter-spacing="-0.02em">{_xml_escape(headline)}</text>

  <!-- Subtext -->
  <text x="{sx:.0f}" y="{sy:.0f}" text-anchor="{sa}"
        fill="{text_fill}" font-size="{sub_size}" font-weight="400"
        opacity="0.80">{_xml_escape(subtext)}</text>

  <!-- Zone label -->
  <text x="{zx + 10}" y="{zy + 18}" font-size="11" fill="#666"
        font-family="monospace">text_zone: {zone}</text>

  <!-- Image-area label (placed away from the text zone) -->
  {_image_area_label(w, h, zone, concept)}

  <!-- Dimension badge -->
  <text x="{w - 10}" y="{h - 10}" text-anchor="end"
        font-size="10" fill="#444" font-family="monospace">{w}×{h}</text>
</svg>"""


def _image_area_label(
    w: int, h: int, zone: str, concept: str
) -> str:
    """Return an SVG <text> element labelling the image area, positioned
    to avoid overlapping the text zone."""
    label = "IMAGE AREA"
    # Place opposite the text zone
    positions: dict[str, tuple[float, float, str]] = {
        "top": (w / 2, h * 0.78, "middle"),
        "bottom": (w / 2, h * 0.22, "middle"),
        "left": (w * 0.68, h / 2, "middle"),
        "right": (w * 0.32, h / 2, "middle"),
        "center": (w / 2, h * 0.88, "middle"),
    }
    x, y, anchor = positions.get(zone, (w / 2, h / 2, "middle"))
    # Concept subtitle on second line
    safe_concept = _xml_escape(concept[:40])
    return (
        f'<text x="{x:.0f}" y="{y:.0f}" text-anchor="{anchor}" '
        f'font-size="13" fill="#3a3a3a" font-family="monospace" '
        f'letter-spacing="0.15em">{label}</text>\n'
        f'<text x="{x:.0f}" y="{y + 16:.0f}" text-anchor="{anchor}" '
        f'font-size="10" fill="#2a2a2a">{safe_concept}</text>'
    )


def _render_palette_swatches(palette: list[str]) -> str:
    """Return HTML for colour-swatch chips."""
    chips: list[str] = []
    for hex_code in palette:
        chips.append(
            f'<div class="swatch">'
            f'<div class="swatch-chip" style="background:{hex_code}"></div>'
            f'<span class="swatch-hex">{hex_code}</span>'
            f"</div>"
        )
    return "\n      ".join(chips)


def _render_typography(card: dict[str, Any]) -> str:
    """Return HTML for the typography info section."""
    layer = _resolve_layer(card)
    fonts = layer["fonts"]
    return f"""\
<div class="typo-grid">
  <span class="typo-label">Headline font</span>
  <span class="typo-value">{_xml_escape(fonts.get("headline_font", "—"))}</span>
  <span class="typo-label">Body font</span>
  <span class="typo-value">{_xml_escape(fonts.get("body_font", "—"))}</span>
  <span class="typo-label">Headline</span>
  <span class="typo-value">{_xml_escape(layer.get("headline", "—"))}</span>
  <span class="typo-label">Subtext</span>
  <span class="typo-value">{_xml_escape(layer.get("subtext", "—"))}</span>
</div>"""


def _render_meta(card: dict[str, Any]) -> str:
    """Return HTML for the top metadata row."""
    parts: list[str] = []
    parts.append(
        f'<span class="zone-tag">text_zone: {_xml_escape(card["text_zone"])}</span>'
    )
    parts.append(
        f"<span>Aspect: <strong>{_xml_escape(card['aspect_ratio'])}</strong></span>"
    )
    parts.append(
        f"<span>Tool: <strong>{_xml_escape(card['target_tool'])}</strong></span>"
    )
    style_name = _resolve_style_name(card)
    if style_name:
        parts.append(f"<span>Style: <strong>{_xml_escape(style_name)}</strong></span>")

    # Contrast ratio badge
    palette = _resolve_layer(card)["color_palette"]
    try:
        _a, _b, ratio = best_contrast_pair(palette)
        ok = ratio >= 4.5
        badge_class = "contrast-ok" if ok else "contrast-bad"
        parts.append(
            f'<span>Contrast: <strong>{ratio:.1f}:1</strong>'
            f'<span class="contrast-badge {badge_class}">'
            f'{"AA ✓" if ok else "FAIL"}</span></span>'
        )
    except Exception:
        parts.append("<span>Contrast: <strong>N/A</strong></span>")

    return "\n    " + "\n    ".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_wireframe(card: dict[str, Any]) -> str:
    """Generate a complete, self-contained HTML wireframe preview from *card*.

    The returned HTML can be saved as a ``.html`` file and opened in any
    browser, or embedded in an iframe.  It requires no external resources.

    Visualised elements
    -------------------
    * Full-canvas SVG showing the image area (hatched) and the text zone
      (highlighted rectangle at the card's ``text_zone`` position).
    * Headline and subtext rendered inside the text zone using colours
      drawn from the palette's best-contrast pair.
    * Colour-palette swatch chips with HEX labels.
    * Typography metadata (headline/subtext fonts and copy).
    * Aspect ratio, target tool, layout style, and WCAG contrast badge.
    """
    layer = _resolve_layer(card)
    palette = layer["color_palette"]
    concept = _xml_escape(card.get("concept", "Untitled"))

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CaVDesign Wireframe — {concept}</title>
<style>
{_CSS}
</style>
</head>
<body>
<div class="wireframe-card">
  <h1>{concept}</h1>
  <div class="meta-row">
    {_render_meta(card)}
  </div>

  <!-- Canvas wireframe -->
  <div class="canvas-wrap">
    {_render_svg(card)}
  </div>

  <!-- Colour palette -->
  <div class="section-title">Colour Palette</div>
  <div class="swatches">
    {_render_palette_swatches(palette)}
  </div>

  <!-- Typography -->
  <div class="section-title">Typography &amp; Copy</div>
  {_render_typography(card)}
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Tiny utilities
# ---------------------------------------------------------------------------

_ESCAPE_MAP = str.maketrans({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"})


def _xml_escape(text: str) -> str:
    """Escape ``&``, ``<``, ``>``, ``\"`` for safe XML/HTML embedding."""
    return text.translate(_ESCAPE_MAP)


def _desaturate_hex(hex_color: str, amount: float) -> str:
    """Return a desaturated (mixed-toward-grey) version of *hex_color*.

    *amount* = 0.0 leaves the colour unchanged; 1.0 returns pure grey.
    Used so the wireframe's text-zone tint reads as a highlight, not a
    fully-saturated block that competes with the swatches.
    """
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    grey = int(0.299 * r + 0.587 * g + 0.114 * b)
    r = int(r + (grey - r) * amount)
    g = int(g + (grey - g) * amount)
    b = int(b + (grey - b) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"
