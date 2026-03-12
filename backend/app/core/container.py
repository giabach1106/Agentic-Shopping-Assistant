from __future__ import annotations

from dataclasses import dataclass

from app.collectors.base import RealtimeCollector
from app.core.config import Settings
from app.core.model_router import ModelRouter
from app.memory.session_service import SessionService
from app.orchestrator.graph import AgentOrchestrator
from app.rag.providers import HybridRAGService
from app.services.ingredient_analysis import IngredientAnalyzer
from app.tools.ui_executor import UIExecutor


@dataclass(slots=True)
class ServiceContainer:
    settings: Settings
    model_router: ModelRouter
    rag_service: HybridRAGService
    realtime_collector: RealtimeCollector
    ui_executor: UIExecutor
    session_service: SessionService
    orchestrator: AgentOrchestrator
    ingredient_analyzer: IngredientAnalyzer
