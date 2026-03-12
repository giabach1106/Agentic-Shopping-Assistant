from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateSessionResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    created_at: str = Field(alias="createdAt")


class ChatRequest(BaseModel):
    session_id: str = Field(alias="sessionId")
    message: str = Field(min_length=1, max_length=4_000)


class ChatResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    status: str
    reply: str
    decision: dict[str, Any] | None = None
    scientific_score: dict[str, Any] = Field(alias="scientificScore")
    evidence_stats: dict[str, Any] = Field(alias="evidenceStats")
    trace: list[dict[str, Any]]
    missing_evidence: list[str] = Field(alias="missingEvidence")
    blocking_agents: list[str] = Field(alias="blockingAgents")
    state: dict[str, Any]


class ResumeRunRequest(BaseModel):
    message: str | None = Field(
        default=None,
        description="Optional follow-up response to continue the previous run.",
    )


class MessageItem(BaseModel):
    role: str
    content: str
    created_at: str = Field(alias="createdAt")


class SessionSnapshotResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    messages: list[MessageItem]
    checkpoint_state: dict[str, Any] | None = Field(alias="checkpointState")


class RecommendationResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    status: str
    decision: dict[str, Any] | None
    scientific_score: dict[str, Any] = Field(alias="scientificScore")
    evidence_stats: dict[str, Any] = Field(alias="evidenceStats")
    trace: list[dict[str, Any]]
    missing_evidence: list[str] = Field(alias="missingEvidence")
    blocking_agents: list[str] = Field(alias="blockingAgents")


class HealthResponse(BaseModel):
    status: str
    app: str
    checkpoint_backend: str = Field(alias="checkpointBackend")
    default_model: str = Field(alias="defaultModel")
    fallback_model: str = Field(alias="fallbackModel")


class RuntimeMetricsResponse(BaseModel):
    total_calls: int = Field(alias="totalCalls")
    total_fallback_calls: int = Field(alias="totalFallbackCalls")
    total_estimated_cost_usd: float = Field(alias="totalEstimatedCostUsd")
    tasks: dict[str, Any]
    sessions_tracked: int = Field(alias="sessionsTracked")


class VoiceConsultRequest(BaseModel):
    session_id: str = Field(alias="sessionId")
    question: str = Field(min_length=1, max_length=2_000)


class VoiceConsultResponse(BaseModel):
    session_id: str = Field(alias="sessionId")
    answer: str
    mode: str
    model_meta: dict[str, Any] = Field(alias="modelMeta")
