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


def test_detect_category_english_and_turkish():
    assert detect_category("I want an Instagram post for my cafe") == "instagram_post"
    assert detect_category("Kadikoy icin instagram gonderisi") == "instagram_post"
    assert detect_category("bir sunum hazirla") == "presentation"


def test_detect_category_none_when_no_match():
    assert detect_category("just some random words here") is None
