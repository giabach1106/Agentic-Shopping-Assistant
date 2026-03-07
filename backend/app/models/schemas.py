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
    reply: str
    state: dict[str, Any]


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


class HealthResponse(BaseModel):
    status: str
    app: str
    checkpoint_backend: str = Field(alias="checkpointBackend")
    default_model: str = Field(alias="defaultModel")
    fallback_model: str = Field(alias="fallbackModel")

