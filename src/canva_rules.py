"""Canva knowledge base — the terms, dimensions and library keywords that
Canva's Magic Media / Canva GPT algorithms understand best.

This is the fixed "Canva expertise" the Architect agent (DeepSeek) reasons
over when it turns a plain user request into a technical design brief. Kept
as plain data so both agents and the tests share one source of truth.
"""

from __future__ import annotations

import difflib
import re
from typing import Any

CANVA_KNOWLEDGE_BASE: dict[str, Any] = {
    "dimensions": {
        "instagram_post": "1080x1080 (1:1)",
        "instagram_portrait": "1080x1350 (4:5)",
        "instagram_story": "1080x1920 (9:16)",
        "facebook_post": "1200x630 (1.91:1)",
        "flyer_a4": "2480x3508 (3:4 aspect)",
        "poster": "2480x3508 (3:4 aspect)",
        "presentation": "1920x1080 (16:9)",
        "banner": "1920x1080 (16:9)",
        "youtube_thumbnail": "1280x720 (16:9)",
        "logo": "500x500 (1:1)",
        "business_card": "1050x600 (7:4 aspect)",
    },
    "magic_media_styles": [
        "Vibrant",
        "Minimalist",
        "3D Model",
        "Retro Anime",
        "Watercolor",
        "Cyberpunk",
        "Paper Cut",
        "Flat Vector",
        "Photographic",
        "Concept Art",
        "Neon",
    ],
    "canva_element_keywords": [
        "organic fluid shapes",
        "glassmorphism card overlay",
        "duotone accent",
        "isolated element on transparent background",
        "boho line art",
        "bauhaus geometric layout",
        "flat vector illustration",
        "grainy gradient texture",
        "editorial collage",
        "minimal line icons",
        "risograph print texture",
    ],
    "target_tools": ["Canva Magic Media", "DALL-E 3", "Canva GPT", "Midjourney"],
    "negative_space_rule": (
        "Always reserve deliberate empty negative space (top, bottom, or one "
        "side) so the user can overlay real, crisp typography in Canva without "
        "the generated image's own detail clashing with the text."
    ),
}


# ---------------------------------------------------------------------------
# Category detection — multi-strategy regex scoring + fuzzy fallback
# ---------------------------------------------------------------------------

# Each rule is (regex, category, weight). Weights:
#   1.0  explicit dimension / format specification
#   0.9  compound anchor (platform + content type in same phrase)
#   0.8  named platform
#   0.7  content-type keyword (strong)
#   0.6  content-type keyword (medium)
#   0.5  orientation / shape hint
#   0.4  generic noun (only counts with corroborating evidence)
#
# Patterns accumulate scores per category; the highest-scoring category wins.
# None is returned when no rule fires or the best score is below MIN_SCORE.

MIN_SCORE = 0.6  # reject isolated orientation hints and generic nouns alone


def _rx(pat: str) -> re.Pattern[str]:
    """Compile a regex with case-insensitive flag and extra word-boundary
    anchors stripped — callers manage their own boundaries via \\b or
    look-behind/look-ahead as needed."""
    return re.compile(pat, re.IGNORECASE)


# -- Layer 1: explicit dimensions (weight 1.0) --------------------------------
_DIMENSION_RULES: list[tuple[re.Pattern[str], str, float]] = [
    # Pixel dimensions
    (_rx(r"\b1080\s*[x×]\s*1080\b"), "instagram_post", 1.0),
    (_rx(r"\b1080\s*[x×]\s*1350\b"), "instagram_portrait", 1.0),
    (_rx(r"\b1080\s*[x×]\s*1920\b"), "instagram_story", 1.0),
    (_rx(r"\b1920\s*[x×]\s*1080\b"), "presentation", 1.0),
    (_rx(r"\b1200\s*[x×]\s*630\b"), "facebook_post", 1.0),
    (_rx(r"\b1280\s*[x×]\s*720\b"), "youtube_thumbnail", 1.0),
    (_rx(r"\b500\s*[x×]\s*500\b"), "logo", 1.0),
    (_rx(r"\b1050\s*[x×]\s*600\b"), "business_card", 1.0),
    (_rx(r"\b2480\s*[x×]\s*3508\b"), "poster", 1.0),
    # Named paper sizes
    (_rx(r"\bA4\b"), "flyer_a4", 1.0),
    (_rx(r"\bA5\b"), "flyer_a4", 1.0),
    (_rx(r"\bA3\b"), "poster", 1.0),
    # Named aspect ratios
    (_rx(r"\b1:1\b"), "instagram_post", 1.0),
    (_rx(r"\b4:5\b"), "instagram_portrait", 1.0),
    (_rx(r"\b9:16\b"), "instagram_story", 1.0),
    (_rx(r"\b16:9\b"), "presentation", 1.0),
    (_rx(r"\b3:4\b"), "flyer_a4", 1.0),
    (_rx(r"\b1\.91:1\b"), "facebook_post", 1.0),
]

# -- Layer 2: named platforms (weight 0.8) ------------------------------------
_PLATFORM_RULES: list[tuple[re.Pattern[str], str, float]] = [
    (_rx(r"\binstagram\b|\binsta\b(?:\s*gram\b)?"), "instagram_post", 0.8),
    (_rx(r"\bfacebook\b|\bFB\b"), "facebook_post", 0.8),
    (_rx(r"\byoutube\b|\bYT\b"), "youtube_thumbnail", 0.8),
    (_rx(r"\blinkedin\b"), "presentation", 0.8),
    (_rx(r"\btiktok\b"), "instagram_story", 0.8),
    (_rx(r"\bwhatsapp\b|\bWA\b"), "instagram_story", 0.7),
    (_rx(r"\bpinterest\b"), "instagram_portrait", 0.7),
    (_rx(r"\btwitter\b|\bX\b(?:\s*(?:post|paylaşım))"), "banner", 0.7),
]

# -- Layer 3: content-type keywords (weight 0.6-0.7) --------------------------
_CONTENT_RULES: list[tuple[re.Pattern[str], str, float]] = [
    # Flyer / brochure — Turkish "broşür/brosur" accepts suffixes: broşürü, broşürler
    (_rx(r"\bflyer\b|\bbroşür|\bbrosur|\bel\s*ilanı?\b"), "flyer_a4", 0.7),
    # Poster — Turkish "afiş/afis" accepts suffixes: afişi, afişler
    (_rx(r"\bposter\b|\bafiş|\bafis\b"), "poster", 0.7),
    # Presentation / slides — Turkish "sunum" accepts suffixes: sunumu, sunumlar
    (_rx(r"\bsunum|\bpresentation\b|\bslayt\b|\bslide\b"), "presentation", 0.7),
    # Logo
    (_rx(r"\blogo\b|\blogotype\b"), "logo", 0.7),
    # Business card — Turkish "kartvizit" accepts suffixes: kartviziti, kartvizitler
    (_rx(r"\bkartvizit|\bbusiness\s*card\b|\bcalling\s*card\b"), "business_card", 0.7),
    # Thumbnail / cover — Turkish "kapak" softens k→ğ before vowel suffixes
    # (ünsüz yumuşaması): kapak → kapağı, kapağın
    (_rx(r"\bthumbnail\b|\bkapak|\bkapağ"), "youtube_thumbnail", 0.7),
    # Story / reel — Turkish "hikaye" can surface as hikayesi/hikayeler/etc.
    (_rx(r"\bstory\b|\bstories\b|\bhikaye|\breels?\b"), "instagram_story", 0.7),
    # Carousel
    (_rx(r"\bcarousel\b|\bkarusel\b|\bdöngü\b"), "instagram_post", 0.7),
    # Banner / cover / header
    (_rx(r"\bbanner\b|\bpankart\b|\bheader\b"), "banner", 0.7),
    # Vertical video (9:16 content — Stories / Reels / TikTok).
    # Weight 0.8 beats generic "thumbnail" (0.7) so "dikey video thumbnail"
    # resolves to instagram_story, not youtube_thumbnail.
    (_rx(r"\bdikey\s*video\b|\bvertical\s*video\b"), "instagram_story", 0.8),
    # Invitation / card — Turkish "davetiye/davet" accept suffixes: davetiyesi, davetiyeler
    (_rx(r"\bdavetiye|\binvitation\b|\bdavet\b"), "flyer_a4", 0.6),
    # Menu / price list
    (_rx(r"\bmenü\b|\bmenu\b|\bfiyat\s*listesi\b|\bfiyat\s*list\b"), "flyer_a4", 0.6),
    # Certificate / diploma
    (_rx(r"\bsertifika\b|\bcertificate\b|\bdiploma\b"), "flyer_a4", 0.6),
    # Generic English "post" — low weight, only counts when corroborated
    (_rx(r"\bpost\b(?!er\b|\s*card\b)"), "instagram_post", 0.4),
    # Turkish "gönderi" — stronger than English "post" because in Turkish
    # social-media context it nearly always means an Instagram/social post.
    (_rx(r"\bgönderi"), "instagram_post", 0.6),
]

# -- Layer 4: orientation / shape hints (weight 0.5) ---------------------------
_ORIENTATION_RULES: list[tuple[re.Pattern[str], str, float]] = [
    (_rx(r"\bdikey\b|\bportrait\b|\bvertical\b|\bdik\b"), "instagram_portrait", 0.5),
    (_rx(r"\byatay\b|\blandscape\b|\bhorizontal\b"), "presentation", 0.5),
    (_rx(r"\bkare\b|\bsquare\b"), "instagram_post", 0.5),
]

ALL_RULES: list[tuple[re.Pattern[str], str, float]] = (
    _DIMENSION_RULES + _PLATFORM_RULES + _CONTENT_RULES + _ORIENTATION_RULES
)


# -- Fuzzy lexicon -------------------------------------------------------------
# Normalized keyword → category mapping for difflib fallback when no regex
# matches. Keys are lowercased stems (no inflection), values are canonical
# category ids.  Used only as a last resort — regex wins whenever it fires.

_FUZZY_LEXICON: dict[str, str] = {
    "instagram post": "instagram_post",
    "instagram gonderi": "instagram_post",
    "instagram gönderi": "instagram_post",
    "instagram story": "instagram_story",
    "instagram hikaye": "instagram_story",
    "instagram reel": "instagram_story",
    "instagram portrait": "instagram_portrait",
    "instagram dikey": "instagram_portrait",
    "facebook post": "facebook_post",
    "facebook gonderi": "facebook_post",
    "flyer": "flyer_a4",
    "el ilani": "flyer_a4",
    "el ilanı": "flyer_a4",
    "brosur": "flyer_a4",
    "broşür": "flyer_a4",
    "poster": "poster",
    "afis": "poster",
    "afiş": "poster",
    "presentation": "presentation",
    "sunum": "presentation",
    "slayt": "presentation",
    "slide": "presentation",
    "youtube thumbnail": "youtube_thumbnail",
    "yt kapak": "youtube_thumbnail",
    "thumbnail": "youtube_thumbnail",
    "kapak": "youtube_thumbnail",
    "banner": "banner",
    "pankart": "banner",
    "logo": "logo",
    "business card": "business_card",
    "kartvizit": "business_card",
    "a4 flyer": "flyer_a4",
    "a4 brosur": "flyer_a4",
    "a4 broşür": "flyer_a4",
    "a4 poster": "poster",
    "kare post": "instagram_post",
    "kare gonderi": "instagram_post",
    "dikey post": "instagram_portrait",
    "dikey gonderi": "instagram_portrait",
    "dikey story": "instagram_story",
    "dikey hikaye": "instagram_story",
    "dikey video": "instagram_story",
    "linkedin post": "presentation",
    "linkedin cover": "banner",
    "linkedin banner": "banner",
    "linkedin kapak": "banner",
    "carousel": "instagram_post",
    "karusel": "instagram_post",
    "davetiye": "flyer_a4",
    "invitation": "flyer_a4",
    "menu": "flyer_a4",
    "menü": "flyer_a4",
    "sertifika": "flyer_a4",
    "certificate": "flyer_a4",
}

# Precompute stemmed lexicon keys for fast lookup in _fuzzy_detect.
_FUZZY_KEYS = list(_FUZZY_LEXICON.keys())


def dimensions_for(category: str) -> str | None:
    """Return the Canva dimension string for a known category, or None."""
    return CANVA_KNOWLEDGE_BASE["dimensions"].get(category)


def detect_category(text: str) -> str | None:
    """Detect the most likely design category from a free-text request.

    Uses a three-tier strategy:

    1. **Regex scoring** — four layers of weighted patterns (dimensions,
       platforms, content types, orientation hints) are run against
       *text*. Each match adds its weight to the corresponding category's
       cumulative score. The highest-scoring category above MIN_SCORE
       (0.6) wins.

    2. **Fuzzy matching** — if no regex fires, the lowercased text is
       compared against a lexicon of 50 normalized keyword→category
       entries using ``difflib.get_close_matches`` (cutoff 0.75). Useful
       for slightly inflected or misspelled forms.

    3. **Fallback** — returns None when nothing matches, signalling the
       Architect to reason from scratch.

    Mixed Turkish/English requests are handled naturally because both
    languages appear in the patterns and lexicon.
    """
    lowered = text.lower()
    scores: dict[str, float] = {}

    for pattern, category, weight in ALL_RULES:
        if pattern.search(lowered):
            scores[category] = scores.get(category, 0.0) + weight

    if scores:
        best_cat = max(scores, key=lambda k: scores[k])
        if scores[best_cat] >= MIN_SCORE:
            return best_cat
        # Score exists but too low — fall through to fuzzy

    return _fuzzy_detect(lowered)


def _fuzzy_detect(lowered: str) -> str | None:
    """Last-resort: match *lowered* against the fuzzy lexicon via difflib.

    Returns a category id when a close match is found at cutoff ≥ 0.75,
    or None when nothing is close enough."""
    # Try the full string first
    matches = difflib.get_close_matches(lowered, _FUZZY_KEYS, n=1, cutoff=0.75)
    if matches:
        return _FUZZY_LEXICON[matches[0]]

    # Also try individual words for mixed-language requests like
    # "Linkedin carousel kapağı" where the full phrase isn't in the lexicon
    # but component words might match known entries.
    for word in lowered.split():
        if len(word) < 5:
            continue
        matches = difflib.get_close_matches(word, _FUZZY_KEYS, n=1, cutoff=0.85)
        if matches:
            return _FUZZY_LEXICON[matches[0]]

    return None
