from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.services.trust_scoring import TrustScoringEngine


def _settings(runtime_mode: str = "dev") -> Settings:
    return Settings(
        app_name="test",
        sqlite_path=Path("unused.sqlite3"),
        redis_url="redis://localhost:6399/0",
        redis_key_prefix="test:key",
        aws_region="us-east-1",
        aws_bedrock_kb_id=None,
        default_model_id="pro-model",
        fallback_model_id="lite-model",
        model_timeout_seconds=1.0,
        latency_threshold_seconds=0.5,
        max_retries=1,
        mock_model=True,
        rag_backend="inmemory",
        rag_top_k=3,
        rag_chroma_path=Path("./tmp-chroma"),
        rag_collection_name="shopping_reviews_test",
        ui_executor_backend="mock",
        stop_before_pay=True,
        max_model_calls_per_session=50,
        max_estimated_cost_per_session_usd=1.0,
        estimated_cost_per_call_pro_usd=0.01,
        estimated_cost_per_call_lite_usd=0.004,
        runtime_mode=runtime_mode,
    )


def test_trust_scoring_returns_buy_for_strong_signals() -> None:
    engine = TrustScoringEngine(_settings())
    result = engine.evaluate(
        agent_outputs={
            "collect": {"sourceCoverage": 3},
            "review": {
                "confidence": 0.9,
                "paidPromoLikelihood": 0.05,
                "evidenceQualityScore": 0.9,
                "duplicateReviewClusters": [],
                "riskFlags": [],
                "absaSignals": {
                    "comfort": 0.9,
                    "durability": 0.8,
                    "assembly": 0.6,
                    "price": 0.7,
                    "delivery": 0.75,
                    "return": 0.8,
                },
                "reviewCount": 25,
                "ratingSummary": {
                    "avgRating": 4.8,
                    "ratingCount": 1200,
                    "positiveCount": 1080,
                },
            },
            "visual": {
                "status": "OK",
                "authenticityScore": 88,
                "confidence": 0.82,
                "mismatchFlags": [],
                "visualRisks": [],
            },
            "price": {
                "candidates": [
                    {
                        "title": "A",
                        "sourceUrl": "https://amazon.com/dp/B0CMFQ7Y7Q",
                        "price": 120,
                        "shippingETA": "2-4 days",
                        "returnPolicy": "30-day return",
                    }
                ],
                "blockers": [],
            },
        },
        constraints={"budgetMax": 150, "deliveryDeadline": "friday"},
    )
    assert result.status == "OK"
    assert result.decision is not None
    assert result.decision.verdict == "BUY"
    assert result.scientific_score["finalTrust"] >= 75
    assert result.scientific_score["ratingReliability"] > 0.8


def test_trust_scoring_returns_avoid_for_severe_review_risk() -> None:
    engine = TrustScoringEngine(_settings())
    result = engine.evaluate(
        agent_outputs={
            "collect": {"sourceCoverage": 3},
            "review": {
                "confidence": 0.5,
                "paidPromoLikelihood": 0.95,
                "evidenceQualityScore": 0.2,
                "duplicateReviewClusters": [{"canonicalDocId": "x", "members": ["x", "y"], "sources": ["tiktok"], "size": 2}],
                "riskFlags": ["Possible manipulation"],
                "absaSignals": {"comfort": -0.5, "durability": -0.7},
                "reviewCount": 15,
                "ratingSummary": {
                    "avgRating": 3.0,
                    "ratingCount": 80,
                    "positiveCount": 16,
                },
            },
            "visual": {
                "status": "OK",
                "authenticityScore": 58,
                "confidence": 0.45,
                "mismatchFlags": ["color mismatch"],
                "visualRisks": [],
            },
            "price": {"candidates": [], "blockers": []},
        },
        constraints={"budgetMax": 150, "deliveryDeadline": "tomorrow"},
    )
    assert result.status == "OK"
    assert result.decision is not None
    assert result.decision.verdict == "AVOID"
    assert any("possible manipulation" in flag.lower() for flag in result.decision.risk_flags)


def test_trust_scoring_penalizes_missing_visual_evidence() -> None:
    engine = TrustScoringEngine(_settings())
    result = engine.evaluate(
        agent_outputs={
            "collect": {"sourceCoverage": 3},
            "review": {
                "confidence": 0.78,
                "evidenceQualityScore": 0.8,
                "paidPromoLikelihood": 0.15,
                "duplicateReviewClusters": [],
                "reviewCount": 12,
                "ratingSummary": {
                    "avgRating": 4.3,
                    "ratingCount": 320,
                    "positiveCount": 250,
                },
            },
            "visual": {
                "status": "NEED_MORE_EVIDENCE",
                "authenticityScore": 52,
                "confidence": 0.38,
                "mismatchFlags": [],
                "requiredEvidence": ["close-up material photo"],
                "evidenceRefs": [],
                "visualRisks": ["No user visual evidence available for authenticity check."],
            },
            "price": {"candidates": [], "blockers": []},
        },
        constraints={"budgetMax": 150, "deliveryDeadline": "friday"},
    )
    assert result.status == "OK"
    assert result.decision is not None
    assert "visualEvidence" in result.missing_evidence
    assert result.scientific_score["visualReliability"] < 0.4


def test_trust_scoring_penalizes_automation_blockers() -> None:
    engine = TrustScoringEngine(_settings())
    result = engine.evaluate(
        agent_outputs={
            "collect": {"sourceCoverage": 3},
            "review": {
                "confidence": 0.84,
                "evidenceQualityScore": 0.82,
                "paidPromoLikelihood": 0.2,
                "duplicateReviewClusters": [],
                "reviewCount": 15,
                "ratingSummary": {
                    "avgRating": 4.5,
                    "ratingCount": 500,
                    "positiveCount": 410,
                },
            },
            "visual": {
                "status": "OK",
                "authenticityScore": 82,
                "confidence": 0.72,
                "mismatchFlags": [],
                "requiredEvidence": [],
                "evidenceRefs": ["v1"],
                "visualRisks": [],
            },
            "price": {
                "candidates": [],
                "blockers": ["automation_blocked"],
            },
        },
        constraints={"budgetMax": 150, "deliveryDeadline": "friday"},
    )
    assert result.status == "OK"
    assert result.decision is not None
    assert any("automation_blocked" in flag for flag in result.decision.risk_flags)
    assert result.decision.verdict in {"WAIT", "AVOID"}


def test_trust_scoring_fail_closed_in_prod_mode_when_required_evidence_missing() -> None:
    engine = TrustScoringEngine(_settings(runtime_mode="prod"))
    result = engine.evaluate(
        agent_outputs={
            "collect": {"sourceCoverage": 1},
            "review": {
                "reviewCount": 1,
                "ratingSummary": {"avgRating": 4.6, "ratingCount": 2, "positiveCount": 2},
            },
            "visual": {"status": "NEED_MORE_EVIDENCE", "authenticityScore": 45, "confidence": 0.3},
            "price": {"blockers": ["executor_not_realtime"], "candidates": []},
        },
        constraints={"budgetMax": 150},
    )
    assert result.status == "NEED_DATA"
    assert result.decision is None
    assert set(result.blocking_agents) >= {"collect", "review", "visual", "price"}
