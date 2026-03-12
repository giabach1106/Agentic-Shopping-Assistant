from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(slots=True)
class VisualAnalysisResult:
    status: Literal["OK", "NEED_MORE_EVIDENCE"]
    authenticity_score: int
    mismatch_flags: list[str]
    visual_risks: list[str]
    confidence: float
    required_evidence: list[str]
    evidence_refs: list[str]


class VisualEvidenceAnalyzer:
    def analyze(self, evidence_refs: list[str]) -> VisualAnalysisResult:
        normalized = [item.lower() for item in evidence_refs]
        if len(normalized) == 0:
            return VisualAnalysisResult(
                status="NEED_MORE_EVIDENCE",
                authenticity_score=45,
                mismatch_flags=[],
                visual_risks=["No user visual evidence available for authenticity check."],
                confidence=0.3,
                required_evidence=[
                    "One unedited user-taken photo in room lighting.",
                    "One close-up photo showing material texture.",
                ],
                evidence_refs=[],
            )

        authenticity = 82
        confidence = 0.74
        mismatch_flags: list[str] = []
        visual_risks: list[str] = []

        if any("blurry" in item for item in normalized):
            authenticity -= 14
            confidence -= 0.12
            visual_risks.append("Evidence contains blurry images that reduce verification quality.")

        if any(term in item for item in normalized for term in ("ai", "synthetic", "generated")):
            authenticity -= 22
            confidence -= 0.15
            visual_risks.append("Potential AI-generated imagery signal detected.")

        if any("color-mismatch" in item or "different-color" in item for item in normalized):
            authenticity -= 10
            mismatch_flags.append("Reported color mismatch between listing and real-world photo.")

        if any("scale-issue" in item or "size-off" in item for item in normalized):
            authenticity -= 8
            mismatch_flags.append("Possible scale mismatch relative to room dimensions.")

        authenticity = max(0, min(100, authenticity))
        confidence = max(0.0, min(1.0, confidence))

        return VisualAnalysisResult(
            status="OK",
            authenticity_score=authenticity,
            mismatch_flags=mismatch_flags,
            visual_risks=visual_risks,
            confidence=round(confidence, 2),
            required_evidence=[],
            evidence_refs=evidence_refs,
        )
