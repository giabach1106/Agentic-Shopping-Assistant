from __future__ import annotations

from app.orchestrator.search_brief import SearchBrief


def test_search_brief_dedupes_repeated_terms_for_supplement() -> None:
    brief = SearchBrief.from_constraints(
        {
            "category": "whey isolate",
            "mustHave": ["whey isolate", "whey", "protein"],
            "deliveryDeadline": None,
        }
    )
    amazon_query = brief.query_for("amazon")
    assert amazon_query.count("whey") == 1
    assert amazon_query.count("isolate") == 1


def test_search_brief_builds_domain_specific_chair_queries() -> None:
    brief = SearchBrief.from_constraints(
        {
            "category": "ergonomic office chair",
            "mustHave": ["ergonomic", "fast delivery"],
            "deliveryDeadline": "fast delivery",
        }
    )
    assert "lumbar" in brief.query_for("ebay")
    assert "mesh" in brief.query_for("walmart")
    assert "review" in brief.query_for("reddit")
