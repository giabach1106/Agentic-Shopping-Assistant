from __future__ import annotations

import re
from typing import Any


class IngredientAnalyzer:
    _beneficial_terms = {
        "whey isolate": "High protein purity with lower lactose.",
        "hydrolyzed whey": "Fast absorption profile for post-workout use.",
        "digestive enzyme": "May improve tolerance for sensitive users.",
        "probiotic": "Supports digestion and gut comfort.",
        "third-party tested": "Independent verification signal for label trust.",
        "informed sport": "Third-party certification against banned substances.",
        "bcaa": "Supports recovery and amino acid density.",
        "leucine": "Strong muscle protein synthesis support.",
    }
    _risk_terms = {
        "sucralose": "Artificial sweetener that some users avoid.",
        "acesulfame potassium": "Artificial sweetener often paired with sucralose.",
        "soy lecithin": "Potential allergen depending on user preference.",
        "gum blend": "Texture additive that can cause GI issues for some users.",
        "proprietary blend": "Opaque dosing reduces formulation trust.",
        "maltodextrin": "Fast carb filler that may dilute protein-first value.",
    }
    _protein_signals = (
        "whey isolate",
        "hydrolyzed whey",
        "whey concentrate",
        "casein",
        "plant protein",
        "pea protein",
        "collagen",
    )

    def analyze(
        self,
        *,
        title: str,
        description: str,
        review_texts: list[str],
        evidence_refs: list[str],
        source_url: str,
    ) -> dict[str, Any]:
        corpus = " ".join([title, description, *review_texts]).lower()
        beneficial = self._extract_matches(corpus, self._beneficial_terms)
        risks = self._extract_matches(corpus, self._risk_terms)
        protein_source = self._detect_protein_source(corpus)

        base_score = 74
        if protein_source in {"whey isolate", "hydrolyzed whey"}:
            base_score += 8
        if any(item["ingredient"] == "third-party tested" for item in beneficial):
            base_score += 6
        if any(item["ingredient"] == "informed sport" for item in beneficial):
            base_score += 4
        base_score -= min(18, len(risks) * 6)
        if protein_source == "unknown":
            base_score -= 8

        confidence = 0.45
        confidence += min(0.25, len(review_texts) * 0.04)
        confidence += min(0.2, len(beneficial) * 0.05)
        confidence = min(0.96, round(confidence, 2))

        summary_parts = []
        if protein_source != "unknown":
            summary_parts.append(f"Protein source detected: {protein_source}.")
        if beneficial:
            summary_parts.append(
                "Positive signals include " + ", ".join(item["ingredient"] for item in beneficial[:3]) + "."
            )
        if risks:
            summary_parts.append(
                "Watchouts include " + ", ".join(item["ingredient"] for item in risks[:3]) + "."
            )
        if not summary_parts:
            summary_parts.append("Ingredient evidence is limited; rely on broader trust signals.")

        references = []
        for ref in evidence_refs:
            item = str(ref).strip()
            if item and item not in references:
                references.append(item)
        if source_url and source_url not in references:
            references.append(source_url)

        return {
            "score": max(0, min(100, base_score)),
            "summary": " ".join(summary_parts),
            "proteinSource": protein_source,
            "beneficialSignals": beneficial,
            "redFlags": risks,
            "confidence": confidence,
            "references": references[:8],
        }

    def _extract_matches(
        self,
        corpus: str,
        lookup: dict[str, str],
    ) -> list[dict[str, str]]:
        matches: list[dict[str, str]] = []
        for term, note in lookup.items():
            if re.search(rf"\b{re.escape(term)}\b", corpus):
                matches.append({"ingredient": term, "note": note})
        return matches

    def _detect_protein_source(self, corpus: str) -> str:
        for term in self._protein_signals:
            if term in corpus:
                return term
        return "unknown"
