from __future__ import annotations

from typing import Any


def _join_top(items: list[str], limit: int = 3) -> str:
    visible = [str(item).strip() for item in items if str(item).strip()][:limit]
    if not visible:
        return ""
    return ", ".join(visible)


def format_follow_up_reply(question: str, missing_fields: list[str]) -> str:
    missing = _join_top(missing_fields, limit=4)
    if missing:
        return f"{question} I still need: {missing}."
    return question


def format_need_data_reply(
    missing_evidence: list[str],
    blocking_agents: list[str],
) -> str:
    missing = _join_top(missing_evidence, limit=4)
    blockers = _join_top(blocking_agents, limit=3)
    if missing and blockers:
        return (
            "I need a bit more evidence before giving a final verdict. "
            f"Missing: {missing}. Current blockers: {blockers}. "
            "Reply with one more constraint or preference and I will continue this same session."
        )
    if missing:
        return (
            "I need a bit more evidence before giving a final verdict. "
            f"Missing: {missing}. Reply with one more constraint to continue."
        )
    return (
        "I need one more follow-up detail before finalizing the recommendation. "
        "Reply in this session and I will continue."
    )


def format_decision_reply(
    decision: dict[str, Any],
    scientific_score: dict[str, Any],
) -> str:
    verdict = str(decision.get("verdict") or "PENDING").upper()
    trust = scientific_score.get("finalTrust")
    trust_text = (
        f"{float(trust):.2f}" if isinstance(trust, (float, int)) else "n/a"
    )
    reasons = decision.get("topReasons") or []
    if isinstance(reasons, list) and reasons:
        lead = str(reasons[0]).strip()
    else:
        lead = "Decision synthesized from price, evidence quality, and trust scoring."
    return f"{verdict} at trust {trust_text}. {lead}"


def build_assistant_meta(
    *,
    reply: str,
    decision: dict[str, Any] | None,
    scientific_score: dict[str, Any],
    missing_evidence: list[str],
    blocking_agents: list[str],
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    verdict = None
    top_reasons: list[str] = []
    if isinstance(decision, dict):
        verdict = decision.get("verdict")
        raw_reasons = decision.get("topReasons")
        if isinstance(raw_reasons, list):
            top_reasons = [str(item).strip() for item in raw_reasons if str(item).strip()]
    return {
        "summary": reply,
        "verdict": verdict,
        "trust": scientific_score.get("finalTrust"),
        "topReasons": top_reasons[:3],
        "missingEvidence": list(missing_evidence)[:6],
        "blockingAgents": list(blocking_agents)[:4],
        "traceRef": "recommendation.trace",
        "traceCount": len(trace),
    }
