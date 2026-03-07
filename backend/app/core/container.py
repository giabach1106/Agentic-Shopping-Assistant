from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.core.model_router import ModelRouter
from app.memory.session_service import SessionService
from app.orchestrator.graph import AgentOrchestrator
from app.rag.providers import HybridRAGService


@dataclass(slots=True)
class ServiceContainer:
    settings: Settings
    model_router: ModelRouter
    rag_service: HybridRAGService
    session_service: SessionService
    orchestrator: AgentOrchestrator
