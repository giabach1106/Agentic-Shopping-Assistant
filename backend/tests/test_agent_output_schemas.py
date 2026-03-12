from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.agent_outputs import CandidateProduct, PriceLogisticsOutput, VisualInsight


def test_candidate_product_rejects_non_positive_price() -> None:
    with pytest.raises(ValidationError):
        CandidateProduct(
            title="Broken price",
            sourceUrl="https://example.com/item",
            price=0,
            rating=4.0,
            shippingETA="2-4 days",
            returnPolicy="30-day return",
            checkoutReady=True,
            evidenceRefs=["ref-1"],
        )


def test_price_logistics_output_enforces_stop_before_pay() -> None:
    with pytest.raises(ValidationError):
        PriceLogisticsOutput(
            candidates=[],
            executionTrace=[],
            blockers=[],
            consentAutofill=False,
            stopBeforePay=False,
        )


def test_visual_insight_requires_required_evidence_when_needed() -> None:
    with pytest.raises(ValidationError):
        VisualInsight(
            status="NEED_MORE_EVIDENCE",
            authenticityScore=40,
            mismatchFlags=[],
            visualRisks=["No visual proof"],
            confidence=0.2,
            requiredEvidence=[],
            evidenceRefs=[],
        )

