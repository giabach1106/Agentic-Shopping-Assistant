from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.core.container import ServiceContainer
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    CreateSessionResponse,
    HealthResponse,
    SessionSnapshotResponse,
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
    orchestration = await services.orchestrator.run_turn(
        session_id=payload.session_id,
        user_message=payload.message,
        history=history,
    )
    await services.session_service.add_assistant_message(
        payload.session_id, orchestration.reply
    )
    await services.session_service.save_state(payload.session_id, orchestration.state)

    return ChatResponse(
        sessionId=payload.session_id,
        reply=orchestration.reply,
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

