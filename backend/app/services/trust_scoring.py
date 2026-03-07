from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


@dataclass(slots=True)
class TrustScoreResult:
    trust_score: float
    verdict: str
    top_reasons: list[str]
    risk_flags: list[str]
    confidence: float
    why_ranked_here: list[str]
    score_breakdown: dict[str, dict[str, float]]
    selected_candidate: dict[str, Any] | None


class TrustScoringEngine:
    def evaluate(
        self,
        agent_outputs: dict[str, Any],
        constraints: dict[str, Any] | None = None,
    ) -> TrustScoreResult:
        constraints = constraints or {}
        review = agent_outputs.get("review", {})
        visual = agent_outputs.get("visual", {})
        price_payload = agent_outputs.get("price", {})
        review_evidence_refs = [str(item) for item in review.get("evidenceRefs", [])]
        visual_evidence_refs = [str(item) for item in visual.get("evidenceRefs", [])]

        review_score, review_notes, review_risks = self._score_review_authenticity(review)
        visual_score, visual_notes, visual_risks = self._score_visual_reliability(visual)
        logistics_eval = self._score_logistics(price_payload, constraints)

        weighted_review = 30 * review_score
        weighted_visual = 20 * visual_score
        weighted_price = 25 * logistics_eval["price_fairness"]
        weighted_delivery = 15 * logistics_eval["delivery_safety"]
        weighted_return = 10 * logistics_eval["return_safety"]

        trust_score = round(
            weighted_review
            + weighted_visual
            + weighted_price
            + weighted_delivery
            + weighted_return,
            2,
        )

        risk_flags = [*review_risks, *visual_risks, *logistics_eval["risk_flags"]]
        verdict = self._determine_verdict(trust_score, risk_flags)
        confidence = self._confidence(review, visual, logistics_eval["evidence_coverage"])
        why_ranked_here = [
            *review_notes,
            *visual_notes,
            *logistics_eval["notes"],
        ]
        if review_evidence_refs:
            why_ranked_here.append(
                "Review evidence IDs used: " + ", ".join(review_evidence_refs[:3])
            )
        if visual_evidence_refs:
            why_ranked_here.append(
                "Visual evidence IDs used: " + ", ".join(visual_evidence_refs[:3])
            )
        selected_candidate = logistics_eval["selected_candidate"]
        if selected_candidate is not None:
            why_ranked_here.append(
                "Selected candidate details: "
                f"{selected_candidate.get('title')} @ ${selected_candidate.get('price')} "
                f"({selected_candidate.get('shippingETA')})."
            )

        top_reasons = self._top_reasons(
            weighted_review=weighted_review,
            weighted_visual=weighted_visual,
            weighted_price=weighted_price,
            weighted_delivery=weighted_delivery,
            weighted_return=weighted_return,
        )

        breakdown = {
            "reviewAuthenticity": {
                "normalized": round(review_score, 3),
                "weightedPoints": round(weighted_review, 2),
            },
            "visualReliability": {
                "normalized": round(visual_score, 3),
                "weightedPoints": round(weighted_visual, 2),
            },
            "priceFairness": {
                "normalized": round(logistics_eval["price_fairness"], 3),
                "weightedPoints": round(weighted_price, 2),
            },
            "deliverySafety": {
                "normalized": round(logistics_eval["delivery_safety"], 3),
                "weightedPoints": round(weighted_delivery, 2),
            },
            "returnPolicySafety": {
                "normalized": round(logistics_eval["return_safety"], 3),
                "weightedPoints": round(weighted_return, 2),
            },
        }

        return TrustScoreResult(
            trust_score=trust_score,
            verdict=verdict,
            top_reasons=top_reasons,
            risk_flags=risk_flags,
            confidence=confidence,
            why_ranked_here=why_ranked_here,
            score_breakdown=breakdown,
            selected_candidate=selected_candidate,
        )

    def _score_review_authenticity(
        self, review: dict[str, Any]
    ) -> tuple[float, list[str], list[str]]:
        confidence = float(review.get("confidence", 0.5))
        evidence_quality_score = float(review.get("evidenceQualityScore", confidence))
        paid_promo_likelihood = float(review.get("paidPromoLikelihood", 0.0))
        evidence_count = len(review.get("evidenceRefs", []))
        source_diversity = len((review.get("sourceStats") or {}).keys())
        risk_count = len(review.get("riskFlags", []))

        evidence_factor = _clamp(evidence_count / 4.0)
        diversity_factor = _clamp(source_diversity / 3.0)

        base = (
            (0.3 * confidence)
            + (0.3 * evidence_quality_score)
            + (0.2 * evidence_factor)
            + (0.2 * diversity_factor)
        )
        penalty = (0.25 * paid_promo_likelihood) + min(0.2, risk_count * 0.04)
        score = _clamp(base - penalty)

        notes = [
            f"Review evidence coverage: {evidence_count} references across {source_diversity} sources.",
            f"Evidence quality score: {round(evidence_quality_score, 2)}.",
            f"Estimated paid-promotion likelihood: {round(paid_promo_likelihood, 2)}.",
        ]
        risks: list[str] = []
        if paid_promo_likelihood >= 0.7:
            risks.append("High paid-promotion likelihood detected in review corpus.")
        if evidence_count < 2:
            risks.append("Limited review evidence; confidence may be unstable.")
        return score, notes, risks

    def _score_visual_reliability(
        self, visual: dict[str, Any]
    ) -> tuple[float, list[str], list[str]]:
        status = str(visual.get("status", "OK")).upper()
        authenticity = float(visual.get("authenticityScore", 50)) / 100
        confidence = float(visual.get("confidence", 0.5))
        mismatch_count = len(visual.get("mismatchFlags", []))
        evidence_count = len(visual.get("evidenceRefs", []))
        required_evidence_count = len(visual.get("requiredEvidence", []))

        base = (0.62 * authenticity) + (0.28 * confidence) + (0.1 * _clamp(evidence_count / 2))
        penalty = min(0.25, mismatch_count * 0.06)
        if status == "NEED_MORE_EVIDENCE":
            penalty += 0.28
        score = _clamp(base - penalty)

        notes = [
            f"Visual authenticity estimate: {round(authenticity * 100, 1)}%.",
            f"Detected {mismatch_count} visual mismatch flags.",
        ]
        if status == "NEED_MORE_EVIDENCE":
            notes.append(
                f"Visual verification requested {required_evidence_count} additional evidence items."
            )
        risks: list[str] = []
        if status == "NEED_MORE_EVIDENCE":
            risks.append("Visual verification incomplete due to missing image evidence.")
        if authenticity < 0.4:
            risks.append("Low visual authenticity score from image verification.")
        if mismatch_count >= 3:
            risks.append("High number of visual mismatches between listing and UGC photos.")
        return score, notes, risks

    def _score_logistics(
        self,
        price_payload: dict[str, Any],
        constraints: dict[str, Any],
    ) -> dict[str, Any]:
        candidates = price_payload.get("candidates", [])
        blockers = [str(item).lower() for item in price_payload.get("blockers", [])]
        if not candidates:
            risk_flags = ["No candidate data available for logistics scoring."]
            if "automation_blocked" in blockers:
                risk_flags.append(
                    "Checkout automation blocked by anti-bot or access constraints."
                )
            return {
                "price_fairness": 0.5,
                "delivery_safety": 0.5,
                "return_safety": 0.5,
                "notes": [
                    "No candidate data available from price/logistics agent.",
                    (
                        "Execution blockers observed: " + ", ".join(blockers)
                        if blockers
                        else "Execution blockers observed: none"
                    ),
                ],
                "risk_flags": risk_flags,
                "selected_candidate": None,
                "evidence_coverage": 0.0,
            }

        scored_candidates = []
        for candidate in candidates:
            price_score = self._price_fairness(candidate, constraints)
            delivery_score = self._delivery_safety(candidate, constraints)
            return_score = self._return_policy_safety(candidate)
            aggregate = (0.5 * price_score) + (0.3 * delivery_score) + (0.2 * return_score)
            scored_candidates.append(
                {
                    "candidate": candidate,
                    "price_score": price_score,
                    "delivery_score": delivery_score,
                    "return_score": return_score,
                    "aggregate": aggregate,
                }
            )

        scored_candidates.sort(key=lambda item: item["aggregate"], reverse=True)
        best = scored_candidates[0]
        candidate = best["candidate"]
        notes = [
            (
                "Selected candidate "
                f"'{candidate.get('title', 'unknown')}' "
                f"with logistics aggregate score {round(best['aggregate'], 3)}."
            ),
            f"Candidate shipping ETA: {candidate.get('shippingETA', 'unknown')}.",
        ]
        if blockers:
            notes.append("Execution blockers observed: " + ", ".join(blockers))

        risk_flags: list[str] = []
        if "automation_blocked" in blockers:
            risk_flags.append(
                "Checkout automation blocked by anti-bot or access constraints."
            )
            best["delivery_score"] = _clamp(best["delivery_score"] - 0.25)
            best["return_score"] = _clamp(best["return_score"] - 0.12)
        if best["delivery_score"] < 0.45:
            risk_flags.append("Delivery reliability appears weak for the selected offer.")
        if best["return_score"] < 0.45:
            risk_flags.append("Return policy safety is weak for the selected offer.")

        return {
            "price_fairness": best["price_score"],
            "delivery_safety": best["delivery_score"],
            "return_safety": best["return_score"],
            "notes": notes,
            "risk_flags": risk_flags,
            "selected_candidate": candidate,
            "evidence_coverage": _clamp((len(candidates) - len(blockers)) / 3.0),
        }

    def _price_fairness(self, candidate: dict[str, Any], constraints: dict[str, Any]) -> float:
        budget = constraints.get("budgetMax")
        price = candidate.get("price")
        if budget in (None, 0) or price is None:
            return 0.65

        budget_value = float(budget)
        price_value = float(price)
        ratio = price_value / budget_value
        if ratio <= 0.75:
            return 0.95
        if ratio <= 1.0:
            return 0.85
        if ratio <= 1.1:
            return 0.65
        if ratio <= 1.25:
            return 0.45
        return 0.25

    def _delivery_safety(self, candidate: dict[str, Any], constraints: dict[str, Any]) -> float:
        eta = str(candidate.get("shippingETA", "")).lower()
        deadline = str(constraints.get("deliveryDeadline", "")).lower()
        days = self._extract_shipping_days(eta)

        if days is None:
            baseline = 0.55
        elif days <= 2:
            baseline = 0.95
        elif days <= 4:
            baseline = 0.8
        elif days <= 7:
            baseline = 0.6
        else:
            baseline = 0.4

        if deadline and any(day in deadline for day in ("today", "tomorrow")) and (days or 99) > 2:
            baseline -= 0.25
        return _clamp(baseline)

    def _return_policy_safety(self, candidate: dict[str, Any]) -> float:
        policy = str(candidate.get("returnPolicy", "")).lower()
        if "final sale" in policy or "no return" in policy:
            return 0.15

        days_match = re.search(r"(\d+)\s*-?\s*day", policy)
        if not days_match:
            return 0.55
        days = int(days_match.group(1))
        if days >= 30:
            return 0.9
        if days >= 14:
            return 0.75
        if days >= 7:
            return 0.55
        return 0.35

    def _extract_shipping_days(self, eta: str) -> int | None:
        if "same day" in eta:
            return 0
        range_match = re.search(r"(\d+)\s*-\s*(\d+)\s*day", eta)
        if range_match:
            return int(range_match.group(2))
        single_match = re.search(r"(\d+)\s*day", eta)
        if single_match:
            return int(single_match.group(1))
        return None

    def _determine_verdict(self, trust_score: float, risk_flags: list[str]) -> str:
        severe_risk_markers = (
            "High paid-promotion likelihood",
            "Low visual authenticity",
        )
        if any(marker in flag for marker in severe_risk_markers for flag in risk_flags):
            if trust_score < 78:
                return "AVOID"

        if trust_score >= 75:
            return "BUY"
        if trust_score >= 55:
            return "WAIT"
        return "AVOID"

    def _confidence(
        self,
        review: dict[str, Any],
        visual: dict[str, Any],
        evidence_coverage: float,
    ) -> float:
        review_conf = float(review.get("confidence", 0.6))
        visual_conf = float(visual.get("confidence", 0.6))
        confidence = (0.45 * review_conf) + (0.35 * visual_conf) + (0.2 * evidence_coverage)
        return round(_clamp(confidence), 2)

    def _top_reasons(
        self,
        weighted_review: float,
        weighted_visual: float,
        weighted_price: float,
        weighted_delivery: float,
        weighted_return: float,
    ) -> list[str]:
        components = [
            ("Review authenticity signals are strong.", weighted_review),
            ("Visual verification indicates acceptable listing reliability.", weighted_visual),
            ("Price fairness is competitive for the stated budget.", weighted_price),
            ("Shipping risk is manageable for the target delivery window.", weighted_delivery),
            ("Return policy safety is acceptable.", weighted_return),
        ]
        ranked = sorted(components, key=lambda item: item[1], reverse=True)
        return [item[0] for item in ranked[:3]]
