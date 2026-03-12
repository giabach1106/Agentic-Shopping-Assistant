from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.core.container import ServiceContainer
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    CreateSessionResponse,
    HealthResponse,
    RecommendationResponse,
    RuntimeMetricsResponse,
    ResumeRunRequest,
    SessionListResponse,
    SessionProductsEnvelopeResponse,
    SessionSnapshotResponse,
    VoiceConsultRequest,
    VoiceConsultResponse,
)

router = APIRouter()


def _services(request: Request) -> ServiceContainer:
    return request.app.state.services


def _decode_token_claims(authorization: str | None) -> dict[str, Any]:
    if not authorization:
        return {}
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return {}
    token = parts[1]
    payload = token.split(".")
    if len(payload) < 2:
        return {}
    encoded = payload[1] + "=" * (-len(payload[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(encoded.encode("utf-8"))
        loaded = json.loads(decoded.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _product_id(source_url: str, evidence_refs: list[str]) -> str:
    seed = evidence_refs[0] if evidence_refs else source_url
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def _build_session_products(checkpoint: dict[str, Any], services: ServiceContainer) -> dict[str, Any]:
    agent_outputs = dict(checkpoint.get("agent_outputs") or {})
    collection = dict(checkpoint.get("collection") or {})
    price = dict(agent_outputs.get("price") or {})
    review = dict(agent_outputs.get("review") or {})
    decision_block = dict(agent_outputs.get("decision") or {})
    review_texts = [
        str(item.get("review_text") or "")
        for item in collection.get("reviews", [])
        if isinstance(item, dict) and str(item.get("review_text") or "").strip()
    ]
    collect_lookup: dict[str, dict[str, Any]] = {}
    for item in collection.get("products", []):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if url:
            collect_lookup[url] = item

    items: list[dict[str, Any]] = []
    for candidate in price.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        source_url = str(candidate.get("sourceUrl") or "").strip()
        collect_item = collect_lookup.get(source_url, {})
        evidence_refs = [
            str(item).strip()
            for item in candidate.get("evidenceRefs", [])
            if str(item).strip()
        ]
        analysis = services.ingredient_analyzer.analyze(
            title=str(candidate.get("title") or ""),
            description=" ".join(str(item) for item in review.get("pros", [])[:2]),
            review_texts=review_texts,
            evidence_refs=evidence_refs,
            source_url=source_url,
        )
        items.append(
            {
                "productId": _product_id(source_url, evidence_refs),
                "title": candidate.get("title"),
                "storeName": collect_item.get("seller_info")
                or collect_item.get("source")
                or "Marketplace",
                "source": collect_item.get("source") or "unknown",
                "sourceUrl": source_url,
                "price": candidate.get("price"),
                "rating": candidate.get("rating"),
                "shippingETA": candidate.get("shippingETA"),
                "returnPolicy": candidate.get("returnPolicy"),
                "checkoutReady": candidate.get("checkoutReady", False),
                "evidenceRefs": evidence_refs,
                "pros": [str(item) for item in review.get("pros", [])[:4]],
                "cons": [str(item) for item in review.get("cons", [])[:4]],
                "ingredientAnalysis": analysis,
                "scientificScore": decision_block.get("scientificScore", {}),
                "evidenceStats": decision_block.get("evidenceStats", {}),
                "trace": decision_block.get("trace", []),
            }
        )

    return {"sessionId": checkpoint.get("session_id"), "items": items}


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    services = _services(request)
    return HealthResponse(
        status="ok",
        app=services.settings.app_name,
        checkpointBackend=services.session_service.checkpoint_backend,
        defaultModel=services.settings.default_model_id,
        fallbackModel=services.settings.fallback_model_id,
    )


@router.get("/v1/metrics/runtime", response_model=RuntimeMetricsResponse)
async def runtime_metrics(request: Request) -> RuntimeMetricsResponse:
    services = _services(request)
    snapshot = services.model_router.snapshot_metrics()
    return RuntimeMetricsResponse(**snapshot)


@router.post(
    "/v1/sessions",
    response_model=CreateSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(request: Request) -> CreateSessionResponse:
    services = _services(request)
    claims = _decode_token_claims(request.headers.get("Authorization"))
    created = await services.session_service.create_session(
        user_sub=str(claims.get("sub") or "").strip() or None,
        user_email=str(claims.get("email") or "").strip() or None,
    )
    return CreateSessionResponse(**created)


@router.get("/v1/sessions", response_model=SessionListResponse)
async def list_sessions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None),
) -> SessionListResponse:
    services = _services(request)
    claims = _decode_token_claims(request.headers.get("Authorization"))
    result = await services.session_service.list_sessions(
        limit=limit,
        cursor=cursor,
        user_sub=str(claims.get("sub") or "").strip() or None,
    )
    return SessionListResponse(**result)


@router.post("/v1/chat", response_model=ChatResponse)
async def chat(request: Request, payload: ChatRequest) -> ChatResponse:
    services = _services(request)
    claims = _decode_token_claims(request.headers.get("Authorization"))
    user_sub = str(claims.get("sub") or "").strip() or None
    exists = await services.session_service.require_session(payload.session_id, user_sub)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{payload.session_id}' was not found.",
        )

    await services.session_service.add_user_message(payload.session_id, payload.message)
    history = await services.session_service.get_history(payload.session_id)
    previous_checkpoint = await services.session_service.get_checkpoint_state(
        payload.session_id
    )
    orchestration = await services.orchestrator.run_turn(
        session_id=payload.session_id,
        user_message=payload.message,
        history=history,
        previous_state=previous_checkpoint,
    )
    await services.session_service.add_assistant_message(
        payload.session_id, orchestration.reply
    )
    await services.session_service.save_state(payload.session_id, orchestration.state)

    return ChatResponse(
        sessionId=payload.session_id,
        status=orchestration.status,
        reply=orchestration.reply,
        decision=orchestration.decision,
        scientificScore=orchestration.scientific_score,
        evidenceStats=orchestration.evidence_stats,
        trace=orchestration.trace,
        missingEvidence=orchestration.missing_evidence,
        blockingAgents=orchestration.blocking_agents,
        state=orchestration.state,
    )


@router.post("/v1/runs/{session_id}/resume", response_model=ChatResponse)
async def resume_run(
    request: Request,
    session_id: str,
    payload: ResumeRunRequest,
) -> ChatResponse:
    services = _services(request)
    claims = _decode_token_claims(request.headers.get("Authorization"))
    user_sub = str(claims.get("sub") or "").strip() or None
    exists = await services.session_service.require_session(session_id, user_sub)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' was not found.",
        )

    previous_checkpoint = await services.session_service.get_checkpoint_state(session_id)
    if previous_checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No checkpoint state found for session '{session_id}'.",
        )

    if previous_checkpoint.get("needs_follow_up") and not payload.message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This run is waiting for follow-up input. "
                "Provide message in request body to resume."
            ),
        )

    user_message = payload.message or "continue with existing constraints"
    await services.session_service.add_user_message(session_id, user_message)
    history = await services.session_service.get_history(session_id)
    orchestration = await services.orchestrator.run_turn(
        session_id=session_id,
        user_message=user_message,
        history=history,
        previous_state=previous_checkpoint,
    )
    await services.session_service.add_assistant_message(session_id, orchestration.reply)
    await services.session_service.save_state(session_id, orchestration.state)

    return ChatResponse(
        sessionId=session_id,
        status=orchestration.status,
        reply=orchestration.reply,
        decision=orchestration.decision,
        scientificScore=orchestration.scientific_score,
        evidenceStats=orchestration.evidence_stats,
        trace=orchestration.trace,
        missingEvidence=orchestration.missing_evidence,
        blockingAgents=orchestration.blocking_agents,
        state=orchestration.state,
    )


@router.get("/v1/sessions/{session_id}", response_model=SessionSnapshotResponse)
async def get_session(request: Request, session_id: str) -> SessionSnapshotResponse:
    services = _services(request)
    claims = _decode_token_claims(request.headers.get("Authorization"))
    user_sub = str(claims.get("sub") or "").strip() or None
    exists = await services.session_service.require_session(session_id, user_sub)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' was not found.",
        )
    snapshot = await services.session_service.get_snapshot(session_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' was not found.",
        )
    return SessionSnapshotResponse(**snapshot)


@router.get("/v1/sessions/{session_id}/products", response_model=SessionProductsEnvelopeResponse)
async def get_session_products(
    request: Request,
    session_id: str,
) -> SessionProductsEnvelopeResponse:
    services = _services(request)
    claims = _decode_token_claims(request.headers.get("Authorization"))
    user_sub = str(claims.get("sub") or "").strip() or None
    exists = await services.session_service.require_session(session_id, user_sub)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' was not found.",
        )
    checkpoint = await services.session_service.get_checkpoint_state(session_id)
    if checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No product state found for session '{session_id}'.",
        )
    payload = _build_session_products(checkpoint, services)
    if not payload["items"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No product candidates available for session '{session_id}'.",
        )
    payload["sessionId"] = session_id
    return SessionProductsEnvelopeResponse(**payload)


@router.get(
    "/v1/recommendations/{session_id}",
    response_model=RecommendationResponse,
)
async def get_recommendation(
    request: Request,
    session_id: str,
) -> RecommendationResponse:
    services = _services(request)
    claims = _decode_token_claims(request.headers.get("Authorization"))
    user_sub = str(claims.get("sub") or "").strip() or None
    exists = await services.session_service.require_session(session_id, user_sub)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' was not found.",
        )
    checkpoint = await services.session_service.get_checkpoint_state(session_id)
    if checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No recommendation state found for session '{session_id}'.",
        )

    decision = (checkpoint.get("agent_outputs") or {}).get("decision")
    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision output is not available for session '{session_id}' yet.",
        )

    return RecommendationResponse(
        sessionId=session_id,
        status=decision.get("status", "ERROR"),
        decision=decision.get("decision"),
        scientificScore=decision.get("scientificScore", {}),
        evidenceStats=decision.get("evidenceStats", {}),
        trace=decision.get("trace", []),
        missingEvidence=decision.get("missingEvidence", []),
        blockingAgents=decision.get("blockingAgents", []),
    )


@router.post("/v1/voice/consult", response_model=VoiceConsultResponse)
async def voice_consult(
    request: Request,
    payload: VoiceConsultRequest,
) -> VoiceConsultResponse:
    services = _services(request)
    claims = _decode_token_claims(request.headers.get("Authorization"))
    user_sub = str(claims.get("sub") or "").strip() or None
    exists = await services.session_service.require_session(payload.session_id, user_sub)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{payload.session_id}' was not found.",
        )

    checkpoint = await services.session_service.get_checkpoint_state(payload.session_id)
    if checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No checkpoint state found for session '{payload.session_id}'.",
        )

    decision = (checkpoint.get("agent_outputs") or {}).get("decision")
    if decision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision output is not available for session '{payload.session_id}'.",
        )

    recommendation = decision.get("decision", {})
    model_result = await services.model_router.call(
        task_type="voice_consultation",
        payload={
            "prompt": (
                "You are a concise shopping consultant. "
                f"Question: {payload.question}. "
                f"Current recommendation: verdict={recommendation.get('verdict')}, "
                f"trustScore={recommendation.get('finalTrust')}, "
                f"topReasons={recommendation.get('topReasons')}, "
                f"riskFlags={recommendation.get('riskFlags')}."
            )
        },
        session_id=payload.session_id,
    )

    answer = (
        f"[VoiceConsult] Status {decision.get('status')} "
        f"Verdict {recommendation.get('verdict')} "
        f"(Trust {recommendation.get('finalTrust')}): {model_result.output.get('text')}"
    )
    return VoiceConsultResponse(
        sessionId=payload.session_id,
        answer=answer,
        mode="text-simulated-voice",
        modelMeta={
            "modelId": model_result.model_id,
            "fallbackUsed": model_result.fallback_used,
            "fallbackReason": model_result.fallback_reason,
        },
    )
