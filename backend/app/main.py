from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.concierge import ConciergeAgent
from app.agents.stubs import (
    CoverageAuditorAgent,
    DecisionAgent,
    EvidenceCollectionAgent,
    PlannerAgent,
    PriceLogisticsAgent,
    ReviewIntelligenceAgent,
    VisualVerificationAgent,
)
from app.api.routes import router as api_router
from app.core.config import Settings
from app.core.container import ServiceContainer
from app.core.logging import configure_logging
from app.core.model_router import ModelRouter
from app.memory.evidence_store import SQLiteEvidenceStore
from app.memory.redis_checkpoint import RedisCheckpointStore
from app.memory.session_service import SessionService
from app.memory.sqlite_store import SQLiteSessionStore
from app.orchestrator.graph import AgentOrchestrator
from app.orchestrator.project_profile import build_project_profile
from app.rag.providers import build_rag_service
from app.services.ingredient_analysis import IngredientAnalyzer
from app.tools.ui_executor import build_ui_executor
from app.collectors.realtime import build_realtime_collector


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    resolved_settings = settings or Settings.from_env()
    rag_service = build_rag_service(resolved_settings)
    realtime_collector = build_realtime_collector(resolved_settings)
    ingredient_analyzer = IngredientAnalyzer()

    model_router = ModelRouter(resolved_settings)
    ui_executor = build_ui_executor(resolved_settings, model_router)
    project_profile = build_project_profile(resolved_settings)
    concierge = ConciergeAgent(model_router, project_profile)
    planner = PlannerAgent(model_router)
    evidence_store = SQLiteEvidenceStore(resolved_settings.sqlite_path)
    coverage_audit = CoverageAuditorAgent(resolved_settings, evidence_store)
    collect = EvidenceCollectionAgent(
        resolved_settings,
        realtime_collector,
        evidence_store,
    )
    review = ReviewIntelligenceAgent(model_router, rag_service)
    visual = VisualVerificationAgent(model_router)
    price = PriceLogisticsAgent(
        model_router=model_router,
        ui_executor=ui_executor,
        stop_before_pay=resolved_settings.stop_before_pay,
        runtime_mode=resolved_settings.runtime_mode,
        ui_executor_backend=resolved_settings.ui_executor_backend,
    )
    decision = DecisionAgent(model_router, resolved_settings)

    orchestrator = AgentOrchestrator(
        concierge=concierge,
        planner=planner,
        coverage_audit=coverage_audit,
        collect=collect,
        review=review,
        visual=visual,
        price=price,
        decision=decision,
    )

    sqlite_store = SQLiteSessionStore(resolved_settings.sqlite_path)
    checkpoint_store = RedisCheckpointStore(
        redis_url=resolved_settings.redis_url,
        key_prefix=resolved_settings.redis_key_prefix,
    )
    session_service = SessionService(sqlite_store, checkpoint_store, evidence_store)

    services = ServiceContainer(
        settings=resolved_settings,
        model_router=model_router,
        rag_service=rag_service,
        realtime_collector=realtime_collector,
        ui_executor=ui_executor,
        session_service=session_service,
        orchestrator=orchestrator,
        ingredient_analyzer=ingredient_analyzer,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await session_service.initialize()
        app.state.services = services
        yield
        await session_service.shutdown()

    app = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_allow_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    app.include_router(api_router)
    return app


app = create_app()
