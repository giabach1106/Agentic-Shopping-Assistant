from __future__ import annotations

from app.collectors.realtime import (
    _detect_marketplace_challenge,
    _extract_amazon_title,
    _extract_rating_and_count,
    _is_product_label_noise,
)


def test_noise_title_detection_filters_rating_labels() -> None:
    assert _is_product_label_noise("28,264 ratings")
    assert _is_product_label_noise("Options: 4 sizes, 11 flavors")
    assert not _is_product_label_noise("Isopure Low Carb Whey Isolate Protein Powder")


def test_marketplace_challenge_detection() -> None:
    ebay_html = "<html><title>Pardon Our Interruption...</title></html>"
    walmart_html = "<html><title>Robot or human?</title><div>px-captcha</div></html>"
    dps_html = "<html><title>Attention Required</title><div>/cdn-cgi/challenge-platform</div></html>"
    assert _detect_marketplace_challenge("ebay", ebay_html) is not None
    assert _detect_marketplace_challenge("walmart", walmart_html) is not None
    assert _detect_marketplace_challenge("dps", dps_html) is not None
    assert _detect_marketplace_challenge("amazon", "<html>normal listing page</html>") is None


def test_rating_count_is_not_accepted_from_loose_pattern_without_rating() -> None:
    rating, count = _extract_rating_and_count("2,851 ratings")
    assert rating == 0.0
    assert count == 0

    rating_structured, count_structured = _extract_rating_and_count('{"ratingCount":28264}')
    assert rating_structured == 0.0
    assert count_structured == 28264

    rating_full, count_full = _extract_rating_and_count(
        'aria-label="4.6 out of 5 stars" 12,345 ratings'
    )
    assert round(rating_full, 1) == 4.6
    assert count_full == 12345


def test_amazon_title_extractor_skips_noise_labels() -> None:
    window = """
    <h2><a><span>2,851 ratings</span></a></h2>
    <h2><a><span>Isopure Zero Carb Whey Protein Isolate Powder</span></a></h2>
    """
    assert _extract_amazon_title(window) == "Isopure Zero Carb Whey Protein Isolate Powder"
