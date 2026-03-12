from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.core.container import ServiceContainer
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    CreateSessionResponse,
    HealthResponse,
    RecommendationResponse,
    RuntimeMetricsResponse,
    ResumeRunRequest,
    SessionSnapshotResponse,
    VoiceConsultRequest,
    VoiceConsultResponse,
)

router = APIRouter()


def _services(request: Request) -> ServiceContainer:
    return request.app.state.services


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
    created = await services.session_service.create_session()
    return CreateSessionResponse(**created)


@router.post("/v1/chat", response_model=ChatResponse)
async def chat(request: Request, payload: ChatRequest) -> ChatResponse:
    services = _services(request)
    exists = await services.session_service.require_session(payload.session_id)
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
    exists = await services.session_service.require_session(session_id)
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
    snapshot = await services.session_service.get_snapshot(session_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' was not found.",
        )
    return SessionSnapshotResponse(**snapshot)


@router.get(
    "/v1/recommendations/{session_id}",
    response_model=RecommendationResponse,
)
async def get_recommendation(
    request: Request,
    session_id: str,
) -> RecommendationResponse:
    services = _services(request)
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
    exists = await services.session_service.require_session(payload.session_id)
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
