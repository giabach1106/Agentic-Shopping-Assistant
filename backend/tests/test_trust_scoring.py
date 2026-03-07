from __future__ import annotations

from app.services.trust_scoring import TrustScoringEngine


def test_trust_scoring_returns_buy_for_strong_signals() -> None:
    engine = TrustScoringEngine()
    result = engine.evaluate(
        agent_outputs={
            "review": {
                "confidence": 0.9,
                "paidPromoLikelihood": 0.1,
                "evidenceRefs": ["a", "b", "c", "d"],
                "sourceStats": {"amazon": 3, "reddit": 2, "tiktok": 1},
                "riskFlags": [],
            },
            "visual": {
                "authenticityScore": 88,
                "confidence": 0.82,
                "mismatchFlags": [],
            },
            "price": {
                "candidates": [
                    {
                        "title": "A",
                        "price": 120,
                        "shippingETA": "2-4 days",
                        "returnPolicy": "30-day return",
                    }
                ]
            },
        },
        constraints={"budgetMax": 150, "deliveryDeadline": "friday"},
    )
    assert result.trust_score >= 75
    assert result.verdict == "BUY"
    assert len(result.top_reasons) >= 1
    assert any("Review evidence IDs used" in item for item in result.why_ranked_here)
    assert any("Selected candidate details" in item for item in result.why_ranked_here)


def test_trust_scoring_returns_avoid_for_severe_review_risk() -> None:
    engine = TrustScoringEngine()
    result = engine.evaluate(
        agent_outputs={
            "review": {
                "confidence": 0.6,
                "paidPromoLikelihood": 0.92,
                "evidenceRefs": ["a"],
                "sourceStats": {"tiktok": 2},
                "riskFlags": ["Possible manipulation"],
            },
            "visual": {
                "authenticityScore": 72,
                "confidence": 0.7,
                "mismatchFlags": [],
            },
            "price": {
                "candidates": [
                    {
                        "title": "B",
                        "price": 145,
                        "shippingETA": "5-7 days",
                        "returnPolicy": "7-day return",
                    }
                ]
            },
        },
        constraints={"budgetMax": 150, "deliveryDeadline": "tomorrow"},
    )
    assert result.verdict == "AVOID"
    assert any("paid-promotion" in flag.lower() for flag in result.risk_flags)


def test_trust_scoring_penalizes_missing_visual_evidence() -> None:
    engine = TrustScoringEngine()
    result = engine.evaluate(
        agent_outputs={
            "review": {
                "confidence": 0.78,
                "evidenceQualityScore": 0.8,
                "paidPromoLikelihood": 0.15,
                "evidenceRefs": ["r1", "r2", "r3"],
                "sourceStats": {"amazon": 2, "reddit": 1},
                "riskFlags": [],
            },
            "visual": {
                "status": "NEED_MORE_EVIDENCE",
                "authenticityScore": 52,
                "confidence": 0.38,
                "mismatchFlags": [],
                "requiredEvidence": ["close-up material photo"],
                "evidenceRefs": [],
            },
            "price": {
                "candidates": [
                    {
                        "title": "C",
                        "price": 130,
                        "shippingETA": "2-4 days",
                        "returnPolicy": "30-day return",
                    }
                ]
            },
        },
        constraints={"budgetMax": 150, "deliveryDeadline": "friday"},
    )
    assert any("missing image evidence" in flag.lower() for flag in result.risk_flags)
    assert result.score_breakdown["visualReliability"]["weightedPoints"] < 12


def test_trust_scoring_penalizes_automation_blockers() -> None:
    engine = TrustScoringEngine()
    result = engine.evaluate(
        agent_outputs={
            "review": {
                "confidence": 0.84,
                "evidenceQualityScore": 0.82,
                "paidPromoLikelihood": 0.2,
                "evidenceRefs": ["r1", "r2", "r3"],
                "sourceStats": {"amazon": 2, "reddit": 1},
                "riskFlags": [],
            },
            "visual": {
                "status": "OK",
                "authenticityScore": 82,
                "confidence": 0.72,
                "mismatchFlags": [],
                "requiredEvidence": [],
                "evidenceRefs": ["v1"],
            },
            "price": {
                "candidates": [
                    {
                        "title": "D",
                        "price": 120,
                        "shippingETA": "2-4 days",
                        "returnPolicy": "30-day return",
                    }
                ],
                "blockers": ["automation_blocked"],
            },
        },
        constraints={"budgetMax": 150, "deliveryDeadline": "friday"},
    )
    assert any("automation blocked" in flag.lower() for flag in result.risk_flags)
    assert result.verdict in {"WAIT", "AVOID"}
