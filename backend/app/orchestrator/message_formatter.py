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


def format_blocked_status_reply(
    *,
    missing_evidence: list[str],
    blocking_agents: list[str],
    coverage_audit: dict[str, Any],
    evidence_stats: dict[str, Any],
) -> str:
    missing = _join_top(missing_evidence, limit=5)
    blockers = _join_top(blocking_agents, limit=4)
    commerce_source_coverage = int(
        evidence_stats.get("commerceSourceCoverage")
        or coverage_audit.get("commerceSourceCoverage")
        or 0
    )
    total_source_coverage = int(
        evidence_stats.get("sourceCoverage")
        or coverage_audit.get("sourceCoverage")
        or 0
    )
    candidate_count = int(
        evidence_stats.get("candidateCount")
        or coverage_audit.get("candidateCount")
        or 0
    )
    blocked_sources = [
        str(item).strip()
        for item in (
            evidence_stats.get("blockedCommerceSources")
            or coverage_audit.get("blockedCommerceSources")
            or []
        )
        if str(item).strip()
    ]

    parts = ["I crawled more evidence, but the session is still blocked."]
    if "sourceCoverage" in missing_evidence:
        if blocked_sources:
            parts.append(
                "Commerce coverage is still "
                f"{commerce_source_coverage} and blocked sources remain: "
                f"{_join_top(blocked_sources, limit=3)}."
            )
        else:
            parts.append(
                f"Commerce coverage is still {commerce_source_coverage} source(s)."
            )
    if candidate_count == 0:
        parts.append(
            "I still have no ranked products that clear the current constraints."
        )
    if missing:
        parts.append(f"Missing: {missing}.")
    if blockers:
        parts.append(f"Current blockers: {blockers}.")
    if total_source_coverage:
        parts.append(f"Total evidence sources seen: {total_source_coverage}.")
    parts.append(
        "Add another preference, relax a constraint, or explicitly ask me to crawl again."
    )
    return " ".join(parts)


def format_confirmation_reply(prompt: str) -> str:
    return prompt.strip() or "I need your confirmation before continuing."


def format_decision_reply(
    decision: dict[str, Any],
    scientific_score: dict[str, Any],
    decision_summary: str | None = None,
) -> str:
    if decision_summary and decision_summary.strip():
        return decision_summary.strip()
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
    conversation_mode: str,
    conversation_intent: str,
    reply_kind: str,
    handled_by: str,
    support_level: str,
    next_actions: list[dict[str, Any]],
    pending_action: dict[str, Any] | None,
    clarification_pending: dict[str, Any] | None = None,
    coverage_confidence: str | None = None,
    checkout_readiness: str | None = None,
    source_health: dict[str, Any] | None = None,
    decision_summary: str | None = None,
    score_breakdown: dict[str, Any] | None = None,
    decision_diagnostics: dict[str, Any] | None = None,
    evidence_diagnostics: dict[str, Any] | None = None,
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
        "decisionSummary": decision_summary,
        "verdict": verdict,
        "trust": scientific_score.get("finalTrust"),
        "topReasons": top_reasons[:3],
        "missingEvidence": list(missing_evidence)[:6],
        "blockingAgents": list(blocking_agents)[:4],
        "traceRef": "recommendation.trace",
        "traceCount": len(trace),
        "conversationMode": conversation_mode,
        "conversationIntent": conversation_intent,
        "replyKind": reply_kind,
        "handledBy": handled_by,
        "supportLevel": support_level,
        "nextActions": list(next_actions)[:6],
        "pendingAction": pending_action,
        "clarificationPending": clarification_pending,
        "coverageConfidence": coverage_confidence,
        "checkoutReadiness": checkout_readiness,
        "sourceHealth": source_health or {},
        "scoreBreakdown": score_breakdown or {},
        "decisionDiagnostics": decision_diagnostics or {},
        "evidenceDiagnostics": evidence_diagnostics or {},
    }
