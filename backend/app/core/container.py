from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.model_router import ModelRouter
from app.memory.session_service import SessionService
from app.orchestrator.graph import AgentOrchestrator


@dataclass(slots=True)
class ServiceContainer:
    settings: Settings
    model_router: ModelRouter
    session_service: SessionService
    orchestrator: AgentOrchestrator

