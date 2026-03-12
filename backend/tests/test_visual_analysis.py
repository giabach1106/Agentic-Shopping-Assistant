from __future__ import annotations

from app.services.visual_analysis import VisualEvidenceAnalyzer


def test_visual_analyzer_requests_more_evidence_when_empty() -> None:
    analyzer = VisualEvidenceAnalyzer()
    result = analyzer.analyze([])
    assert result.status == "NEED_MORE_EVIDENCE"
    assert len(result.required_evidence) > 0
    assert result.confidence < 0.5


def test_visual_analyzer_penalizes_ai_and_blurry_signals() -> None:
    analyzer = VisualEvidenceAnalyzer()
    result = analyzer.analyze(["user-upload-1", "blurry-evidence", "ai-generated-signal"])
    assert result.status == "OK"
    assert result.authenticity_score < 82
    assert any("AI-generated" in risk for risk in result.visual_risks)

