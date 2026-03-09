from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _safe_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(slots=True)
class DecisionPayload:
    verdict: str
    final_trust: float
    confidence: float
    top_reasons: list[str]
    risk_flags: list[str]
    why_ranked_here: list[str]
    selected_candidate: dict[str, Any] | None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "finalTrust": self.final_trust,
            "confidence": self.confidence,
            "topReasons": self.top_reasons,
            "riskFlags": self.risk_flags,
            "whyRankedHere": self.why_ranked_here,
            "selectedCandidate": self.selected_candidate,
        }


@dataclass(slots=True)
class TrustScoreResult:
    status: str
    decision: DecisionPayload | None
    scientific_score: dict[str, float]
    evidence_stats: dict[str, Any]
    trace: list[dict[str, Any]]
    missing_evidence: list[str]
    blocking_agents: list[str]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "decision": self.decision.to_public_dict() if self.decision else None,
            "scientificScore": self.scientific_score,
            "evidenceStats": self.evidence_stats,
            "trace": self.trace,
            "missingEvidence": self.missing_evidence,
            "blockingAgents": self.blocking_agents,
        }


class TrustScoringEngine:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def evaluate(
        self,
        agent_outputs: dict[str, Any],
        constraints: dict[str, Any] | None = None,
    ) -> TrustScoreResult:
        constraints = constraints or {}
        review = dict(agent_outputs.get("review") or {})
        visual = dict(agent_outputs.get("visual") or {})
        price = dict(agent_outputs.get("price") or {})
        collect = dict(agent_outputs.get("collect") or {})

        missing_evidence = list(collect.get("missingEvidence") or [])
        blocking_agents: list[str] = []

        review_count = int(review.get("reviewCount") or 0)
        rating_summary = dict(review.get("ratingSummary") or {})
        rating_count = int(rating_summary.get("ratingCount") or 0)
        source_coverage = int(collect.get("sourceCoverage") or len((review.get("sourceStats") or {}).keys()))
        visual_status = str(visual.get("status") or "NEED_MORE_EVIDENCE").upper()

        if review_count < self._settings.min_review_count:
            missing_evidence.append("reviewCount")
            blocking_agents.append("review")
        if rating_count < self._settings.min_rating_count:
            missing_evidence.append("ratingCount")
            blocking_agents.append("review")
        if source_coverage < self._settings.min_source_coverage:
            missing_evidence.append("sourceCoverage")
            blocking_agents.append("collect")
        if visual_status == "NEED_MORE_EVIDENCE":
            missing_evidence.append("visualEvidence")
            blocking_agents.append("visual")
        if "executor_not_realtime" in (price.get("blockers") or []):
            missing_evidence.append("realtimeExecutor")
            blocking_agents.append("price")

        missing_evidence = sorted(set(missing_evidence))
        blocking_agents = sorted(set(blocking_agents))

        rating_reliability = self._rating_reliability_score(review)
        spam_authenticity = self._spam_authenticity_score(review)
        absa_alignment = self._absa_alignment_score(review, constraints)
        visual_reliability = self._visual_reliability_score(visual)

        final_trust = round(
            100
            * (
                (0.3 * rating_reliability)
                + (0.3 * spam_authenticity)
                + (0.2 * absa_alignment)
                + (0.2 * visual_reliability)
            ),
            2,
        )
        scientific_score = {
            "ratingReliability": round(rating_reliability, 4),
            "spamAuthenticity": round(spam_authenticity, 4),
            "absaAlignment": round(absa_alignment, 4),
            "visualReliability": round(visual_reliability, 4),
            "finalTrust": final_trust,
        }

        evidence_stats = {
            "sourceCoverage": source_coverage,
            "freshnessSeconds": self._freshness_seconds(collect),
            "reviewCount": review_count,
            "ratingCount": rating_count,
            "missingFields": missing_evidence,
        }
        trace = self._build_trace(agent_outputs)

        if missing_evidence and self._settings.runtime_mode == "prod":
            return TrustScoreResult(
                status="NEED_DATA",
                decision=None,
                scientific_score=scientific_score,
                evidence_stats=evidence_stats,
                trace=trace,
                missing_evidence=missing_evidence,
                blocking_agents=blocking_agents,
            )

        verdict = "AVOID"
        if final_trust >= 75:
            verdict = "BUY"
        elif final_trust >= 55:
            verdict = "WAIT"

        risk_flags = [str(item) for item in review.get("riskFlags", [])]
        risk_flags.extend(str(item) for item in visual.get("visualRisks", []))
        risk_flags.extend(str(item) for item in price.get("blockers", []))
        if missing_evidence:
            risk_flags.append(
                "Data completeness below quality gate: " + ", ".join(missing_evidence)
            )

        top_reasons = [
            "Bayesian + Wilson rating reliability calculated from live rating counts.",
            "Opinion authenticity score incorporates promo and duplication signals.",
            "Visual reliability and evidence coverage applied to final trust score.",
        ]
        why_ranked_here = [
            f"ratingReliability={scientific_score['ratingReliability']}",
            f"spamAuthenticity={scientific_score['spamAuthenticity']}",
            f"absaAlignment={scientific_score['absaAlignment']}",
            f"visualReliability={scientific_score['visualReliability']}",
            f"sourceCoverage={source_coverage}, reviewCount={review_count}, ratingCount={rating_count}",
        ]
        decision = DecisionPayload(
            verdict=verdict,
            final_trust=final_trust,
            confidence=round(self._confidence(review, visual, source_coverage), 2),
            top_reasons=top_reasons,
            risk_flags=sorted(set(risk_flags)),
            why_ranked_here=why_ranked_here,
            selected_candidate=self._select_candidate(price),
        )
        return TrustScoreResult(
            status="OK",
            decision=decision,
            scientific_score=scientific_score,
            evidence_stats=evidence_stats,
            trace=trace,
            missing_evidence=missing_evidence,
            blocking_agents=blocking_agents,
        )

    def _rating_reliability_score(self, review: dict[str, Any]) -> float:
        summary = dict(review.get("ratingSummary") or {})
        rating_count = max(0, int(summary.get("ratingCount") or 0))
        avg_rating = float(summary.get("avgRating") or 0.0)
        positive_count = max(0, int(summary.get("positiveCount") or 0))

        # Bayesian average with global prior C and strength m.
        c = self._settings.bayesian_prior_mean
        m = max(1, self._settings.bayesian_prior_strength)
        bayes = ((rating_count * avg_rating) + (m * c)) / (rating_count + m)
        bayes_norm = _clamp((bayes - 1.0) / 4.0)

        # Wilson lower bound for positive ratio (rating >= 4 as positive).
        n = max(1, rating_count)
        p_hat = _clamp(positive_count / n)
        z = self._settings.wilson_confidence_z
        denom = 1 + (z**2 / n)
        centre = p_hat + (z**2 / (2 * n))
        margin = z * math.sqrt((p_hat * (1 - p_hat) + (z**2 / (4 * n))) / n)
        wilson = _clamp((centre - margin) / denom)

        return _clamp((0.6 * bayes_norm) + (0.4 * wilson))

    def _spam_authenticity_score(self, review: dict[str, Any]) -> float:
        promo = _clamp(float(review.get("paidPromoLikelihood") or 0.0))
        duplicates = review.get("duplicateReviewClusters") or []
        dup_penalty = min(0.35, 0.08 * len(duplicates))
        quality = _clamp(float(review.get("evidenceQualityScore") or 0.5))
        return _clamp((0.55 * (1.0 - promo)) + (0.45 * quality) - dup_penalty)

    def _absa_alignment_score(
        self,
        review: dict[str, Any],
        constraints: dict[str, Any],
    ) -> float:
        aspects = dict(review.get("absaSignals") or {})
        if not aspects:
            return 0.5

        weights = {
            "comfort": 0.2,
            "durability": 0.2,
            "assembly": 0.15,
            "price": 0.2,
            "delivery": 0.15,
            "return": 0.1,
        }
        must_have = " ".join(str(item) for item in constraints.get("mustHave", [])).lower()
        if "ergonomic" in must_have:
            weights["comfort"] += 0.15
            weights["durability"] += 0.05
            weights["price"] -= 0.1
            weights["return"] -= 0.1

        total = max(0.0001, sum(max(0.0, val) for val in weights.values()))
        score = 0.0
        for key, weight in weights.items():
            sentiment = float(aspects.get(key) or 0.0)  # -1..1
            normalized = _clamp((sentiment + 1.0) / 2.0)
            score += (max(0.0, weight) / total) * normalized
        return _clamp(score)

    def _visual_reliability_score(self, visual: dict[str, Any]) -> float:
        authenticity = _clamp(float(visual.get("authenticityScore") or 0.0) / 100.0)
        confidence = _clamp(float(visual.get("confidence") or 0.0))
        penalty = 0.28 if str(visual.get("status") or "").upper() == "NEED_MORE_EVIDENCE" else 0
        mismatch_count = len(visual.get("mismatchFlags") or [])
        penalty += min(0.25, mismatch_count * 0.06)
        return _clamp((0.65 * authenticity) + (0.35 * confidence) - penalty)

    def _freshness_seconds(self, collect: dict[str, Any]) -> int:
        collection = dict(collect.get("collection") or {})
        all_records: list[dict[str, Any]] = []
        for key in ("products", "reviews", "visuals"):
            entries = collection.get(key)
            if isinstance(entries, list):
                all_records.extend(item for item in entries if isinstance(item, dict))
        if not all_records:
            return 999999

        now = datetime.now(UTC)
        max_age = 0
        parsed_any = False
        for item in all_records:
            dt = _safe_dt(str(item.get("retrieved_at") or item.get("retrievedAt") or ""))
            if dt is None:
                continue
            parsed_any = True
            max_age = max(max_age, int((now - dt).total_seconds()))
        if not parsed_any:
            return 999999
        return max_age

    def _select_candidate(self, price: dict[str, Any]) -> dict[str, Any] | None:
        candidates = price.get("candidates", [])
        if not isinstance(candidates, list) or len(candidates) == 0:
            return None
        return dict(candidates[0])

    def _confidence(self, review: dict[str, Any], visual: dict[str, Any], source_coverage: int) -> float:
        review_conf = _clamp(float(review.get("confidence") or 0.0))
        visual_conf = _clamp(float(visual.get("confidence") or 0.0))
        coverage = _clamp(source_coverage / max(1, self._settings.min_source_coverage))
        return _clamp((0.45 * review_conf) + (0.35 * visual_conf) + (0.2 * coverage))

    def _build_trace(self, agent_outputs: dict[str, Any]) -> list[dict[str, Any]]:
        trace: list[dict[str, Any]] = []
        collect = dict(agent_outputs.get("collect") or {})
        collection = dict(collect.get("collection") or {})
        collect_trace = collection.get("trace", [])
        if isinstance(collect_trace, list):
            for item in collect_trace:
                if not isinstance(item, dict):
                    continue
                trace.append(
                    {
                        "agent": "collect",
                        "step": item.get("step"),
                        "status": item.get("status"),
                        "detail": item.get("detail"),
                    }
                )
        for name in ("planner", "review", "visual", "price", "decision"):
            node = agent_outputs.get(name)
            if not isinstance(node, dict):
                continue
            status = node.get("status", "OK")
            trace.append({"agent": name, "step": "complete", "status": status})
        return trace
