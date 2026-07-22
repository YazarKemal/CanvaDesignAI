from src.canva_rules import (
    CANVA_KNOWLEDGE_BASE,
    detect_category,
    dimensions_for,
)


def test_knowledge_base_has_core_sections():
    assert "dimensions" in CANVA_KNOWLEDGE_BASE
    assert "magic_media_styles" in CANVA_KNOWLEDGE_BASE
    assert "canva_element_keywords" in CANVA_KNOWLEDGE_BASE
    assert CANVA_KNOWLEDGE_BASE["dimensions"]["instagram_post"] == "1080x1080 (1:1)"


def test_dimensions_for_known_and_unknown():
    assert dimensions_for("instagram_story") == "1080x1920 (9:16)"
    assert dimensions_for("does_not_exist") is None


# -- Regex scoring: explicit dimensions ---------------------------------------


def test_detect_by_pixel_dimensions():
    assert detect_category("1080x1080 banner") == "instagram_post"
    assert detect_category("need 1080×1350 design") == "instagram_portrait"
    assert detect_category("make it 1080x1920") == "instagram_story"
    assert detect_category("1920x1080 slide") == "presentation"
    assert detect_category("1200x630 link image") == "facebook_post"
    assert detect_category("1280x720 thumbnail") == "youtube_thumbnail"
    assert detect_category("500x500 icon") == "logo"
    assert detect_category("1050x600 layout") == "business_card"
    assert detect_category("2480x3508 print") == "poster"


def test_detect_by_paper_size():
    assert detect_category("A4 flyer design") == "flyer_a4"
    assert detect_category("A5 brochure print") == "flyer_a4"
    assert detect_category("A3 poster for the event") == "poster"


def test_detect_by_aspect_ratio():
    assert detect_category("a 1:1 square post") == "instagram_post"
    assert detect_category("4:5 portrait view") == "instagram_portrait"
    assert detect_category("9:16 story format") == "instagram_story"
    assert detect_category("16:9 landscape") == "presentation"
    assert detect_category("3:4 print layout") == "flyer_a4"


# -- Regex scoring: named platforms -------------------------------------------


def test_detect_by_platform_names():
    assert detect_category("instagram post for Monday") == "instagram_post"
    assert detect_category("FB cover photo") == "facebook_post"
    assert detect_category("YT thumbnail redesign") == "youtube_thumbnail"
    assert detect_category("Linkedin carousel kapağı") == "presentation"
    assert detect_category("TikTok video cover") == "instagram_story"
    assert detect_category("WhatsApp status image") == "instagram_story"
    assert detect_category("Pinterest pin design") == "instagram_portrait"


# -- Regex scoring: content types ---------------------------------------------


def test_detect_by_content_type():
    assert detect_category("make a flyer for the event") == "flyer_a4"
    assert detect_category("broşür tasarla") == "flyer_a4"
    assert detect_category("el ilanı hazırla") == "flyer_a4"
    assert detect_category("poster design for concert") == "poster"
    assert detect_category("afiş bastır") == "poster"
    assert detect_category("sunum hazırla") == "presentation"
    assert detect_category("slide deck for pitch") == "presentation"
    assert detect_category("design a logo for my brand") == "logo"
    assert detect_category("kartvizit siparişi") == "business_card"
    assert detect_category("business card design") == "business_card"
    assert detect_category("youtube thumbnail image") == "youtube_thumbnail"
    assert detect_category("story template") == "instagram_story"
    assert detect_category("reels cover") == "instagram_story"
    assert detect_category("carousel post design") == "instagram_post"
    assert detect_category("web banner ad") == "banner"
    assert detect_category("pankart hazırla") == "banner"
    assert detect_category("davetiye tasarımı") == "flyer_a4"
    assert detect_category("wedding invitation card") == "flyer_a4"
    assert detect_category("menü tasarla") == "flyer_a4"
    assert detect_category("sertifika basımı") == "flyer_a4"


# -- Regex scoring: orientation hints -----------------------------------------


def test_detect_by_orientation():
    assert detect_category("dikey post") == "instagram_portrait"
    assert detect_category("portrait mode flyer") == "flyer_a4"
    # "yatay" (0.5) alone is below threshold; pair with a content word
    assert detect_category("yatay sunum") == "presentation"
    assert detect_category("kare gönderi") == "instagram_post"
    assert detect_category("square image for insta") == "instagram_post"


# -- Multi-strategy scoring (accumulated evidence) ----------------------------


def test_platform_and_content_combine_to_correct_category():
    """When multiple rules fire for the same category their weights sum,
    making the correct category win over plausible alternatives."""
    assert detect_category("I want an Instagram post for my cafe") == "instagram_post"
    assert detect_category("Kadikoy icin instagram gonderisi") == "instagram_post"
    assert detect_category("bir sunum hazirla") == "presentation"


def test_mixed_tr_en_requests():
    """Complex mixed-language requests must be categorised correctly."""
    # User's examples from the PR description
    assert detect_category("A4 dikey broşür") == "flyer_a4"
    assert detect_category("Linkedin carousel kapağı") == "presentation"
    # Additional mixed cases
    assert detect_category("YT kapak tasarımı") == "youtube_thumbnail"
    assert detect_category("kare post design") == "instagram_post"
    assert detect_category("16:9 video thumbnail") == "presentation"
    assert detect_category("dikey video kapağı") == "instagram_story"


def test_turkish_inflection_variants():
    """Turkish words with possessive/plural suffixes ('gönderisi',
    'hikayeler', 'kapağı', 'broşürü') must still match their root."""
    assert detect_category("instagram gönderisi için tasarım") == "instagram_post"
    assert detect_category("gönderisini planla") == "instagram_post"
    assert detect_category("hikayeler için dikey şablon") == "instagram_story"
    assert detect_category("hikayesi görüntüleme") == "instagram_story"
    assert detect_category("kapağı yenile") == "youtube_thumbnail"
    assert detect_category("broşürü güncelle") == "flyer_a4"
    assert detect_category("afişi düzenle") == "poster"
    assert detect_category("sunumu kaydet") == "presentation"
    assert detect_category("kartviziti bastır") == "business_card"
    assert detect_category("davetiyesi için tasarım") == "flyer_a4"


def test_vertical_video_beats_generic_thumbnail():
    """'dikey video thumbnail' must resolve to instagram_story (0.8 + 0.7)
    not youtube_thumbnail (0.7) — vertical video is the stronger signal."""
    assert detect_category("dikey video için thumbnail") == "instagram_story"


# -- Fuzzy matching fallback ---------------------------------------------------


def test_detect_category_none_when_no_match():
    assert detect_category("just some random words here") is None


def test_fuzzy_matching_catches_close_matches():
    """When no regex fires, difflib.get_close_matches should catch slight
    misspellings and near-cognate forms."""
    assert detect_category("flyerr design") == "flyer_a4"
    assert detect_category("posterr") == "poster"
    assert detect_category("instgram post") == "instagram_post"


# -- Score threshold -----------------------------------------------------------


def test_low_score_orientation_alone_returns_none():
    """Isolated orientation hints (weight 0.5, below MIN_SCORE 0.6) must
    return None — 'dikey' alone isn't enough to guess a category."""
    assert detect_category("dikey") is None
    assert detect_category("yatay") is None
    assert detect_category("kare") is None
    assert detect_category("portrait") is None
    assert detect_category("landscape") is None


def test_generic_post_alone_returns_none():
    """English 'post' alone (weight 0.4) is below MIN_SCORE — too generic.
    Turkish 'gönderi' (0.6) IS strong enough on its own — in Turkish
    social-media context it nearly always means a social post."""
    assert detect_category("a post about something") is None
    assert detect_category("gönderi") == "instagram_post"


def test_generic_post_with_orientation_sums_past_threshold():
    """'post' (0.4) + 'kare' (0.5) = 0.9, which is above MIN_SCORE."""
    assert detect_category("kare post") == "instagram_post"


# -- Edge cases ----------------------------------------------------------------


def test_all_known_categories_are_detectable():
    """Every category in the knowledge-base dimensions must be reachable
    by the detector via at least one unambiguous input."""
    detectable = {
        "instagram_post": "1080x1080 square post",
        "instagram_portrait": "4:5 portrait post",
        "instagram_story": "9:16 story template",
        "facebook_post": "1200x630 facebook image",
        "flyer_a4": "A4 flyer print",
        "poster": "A3 poster design",
        "presentation": "sunum slaytı hazırla",
        "banner": "web banner design",
        "youtube_thumbnail": "youtube kapak",
        "logo": "logo design for company",
        "business_card": "kartvizit tasarımı",
    }
    for category, text in detectable.items():
        result = detect_category(text)
        assert result == category, f"'{text}' → {result}, expected {category}"
