from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _load_env_file_defaults(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_wrapping_quotes(value.strip())


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _as_csv_tuple(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    items = tuple(part.strip() for part in value.split(",") if part.strip())
    return items or default


@dataclass(slots=True)
class Settings:
    app_name: str
    sqlite_path: Path
    redis_url: str
    redis_key_prefix: str
    aws_region: str
    aws_bedrock_kb_id: str | None
    default_model_id: str
    fallback_model_id: str
    model_timeout_seconds: float
    latency_threshold_seconds: float
    max_retries: int
    mock_model: bool
    rag_backend: str
    rag_top_k: int
    rag_chroma_path: Path
    rag_collection_name: str
    ui_executor_backend: str
    stop_before_pay: bool
    max_model_calls_per_session: int
    max_estimated_cost_per_session_usd: float
    estimated_cost_per_call_pro_usd: float
    estimated_cost_per_call_lite_usd: float
    runtime_mode: str = "dev"
    min_review_count: int = 3
    min_rating_count: int = 10
    min_source_coverage: int = 2
    evidence_freshness_minutes: int = 720
    bayesian_prior_mean: float = 4.0
    bayesian_prior_strength: int = 50
    wilson_confidence_z: float = 1.96
    allow_dev_fallback_in_prod: bool = False
    require_auth: bool = True
    cors_allow_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )
    cognito_region: str | None = None
    cognito_user_pool_id: str | None = None
    cognito_app_client_id: str | None = None
    verify_jwt_signature: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        repo_root = Path(__file__).resolve().parents[3]
        _load_env_file_defaults(repo_root / ".env")

        backend_root = Path(__file__).resolve().parents[2]
        default_db_path = backend_root / "data" / "agent_memory.sqlite3"

        return cls(
            app_name=os.getenv("APP_NAME", "Agentic Shopping Assistant API"),
            sqlite_path=Path(os.getenv("AGENT_SQLITE_PATH", str(default_db_path))),
            redis_url=os.getenv("AGENT_REDIS_URL", "redis://localhost:6379/0"),
            redis_key_prefix=os.getenv(
                "AGENT_REDIS_KEY_PREFIX", "agentic-shopping-assistant:checkpoint"
            ),
            aws_region=os.getenv("AWS_REGION", "us-east-1"),
            aws_bedrock_kb_id=os.getenv("BEDROCK_KB_ID"),
            default_model_id=os.getenv(
                "NOVA_DEFAULT_MODEL_ID", "us.amazon.nova-2-pro-v1:0"
            ),
            fallback_model_id=os.getenv(
                "NOVA_FALLBACK_MODEL_ID", "us.amazon.nova-2-lite-v1:0"
            ),
            model_timeout_seconds=float(os.getenv("MODEL_TIMEOUT_SECONDS", "10")),
            latency_threshold_seconds=float(
                os.getenv("MODEL_LATENCY_THRESHOLD_SECONDS", "6")
            ),
            max_retries=max(1, int(os.getenv("MODEL_MAX_RETRIES", "2"))),
            mock_model=_as_bool(os.getenv("MOCK_MODEL"), default=True),
            rag_backend=os.getenv("RAG_BACKEND", "inmemory"),
            rag_top_k=int(os.getenv("RAG_TOP_K", "5")),
            rag_chroma_path=Path(
                os.getenv("RAG_CHROMA_PATH", str(backend_root / "data" / "chroma"))
            ),
            rag_collection_name=os.getenv("RAG_COLLECTION_NAME", "shopping_reviews"),
            ui_executor_backend=os.getenv("UI_EXECUTOR_BACKEND", "mock"),
            stop_before_pay=_as_bool(os.getenv("STOP_BEFORE_PAY"), default=True),
            max_model_calls_per_session=int(
                os.getenv("MAX_MODEL_CALLS_PER_SESSION", "40")
            ),
            max_estimated_cost_per_session_usd=float(
                os.getenv("MAX_ESTIMATED_COST_PER_SESSION_USD", "0.35")
            ),
            estimated_cost_per_call_pro_usd=float(
                os.getenv("ESTIMATED_COST_PER_CALL_PRO_USD", "0.01")
            ),
            estimated_cost_per_call_lite_usd=float(
                os.getenv("ESTIMATED_COST_PER_CALL_LITE_USD", "0.004")
            ),
            runtime_mode=os.getenv("RUNTIME_MODE", "dev").strip().lower(),
            min_review_count=int(os.getenv("MIN_REVIEW_COUNT", "3")),
            min_rating_count=int(os.getenv("MIN_RATING_COUNT", "10")),
            min_source_coverage=int(os.getenv("MIN_SOURCE_COVERAGE", "2")),
            evidence_freshness_minutes=int(
                os.getenv("EVIDENCE_FRESHNESS_MINUTES", "720")
            ),
            bayesian_prior_mean=float(os.getenv("BAYESIAN_PRIOR_MEAN", "4.0")),
            bayesian_prior_strength=int(os.getenv("BAYESIAN_PRIOR_STRENGTH", "50")),
            wilson_confidence_z=float(os.getenv("WILSON_CONFIDENCE_Z", "1.96")),
            allow_dev_fallback_in_prod=_as_bool(
                os.getenv("ALLOW_DEV_FALLBACK_IN_PROD"), default=False
            ),
            require_auth=_as_bool(os.getenv("AGENT_REQUIRE_AUTH"), default=True),
            cors_allow_origins=_as_csv_tuple(
                os.getenv("AGENT_CORS_ALLOW_ORIGINS") or os.getenv("CORS_ORIGINS"),
                default=("http://localhost:3000", "http://127.0.0.1:3000"),
            ),
            cognito_region=os.getenv("COGNITO_REGION"),
            cognito_user_pool_id=os.getenv("COGNITO_USER_POOL_ID"),
            cognito_app_client_id=os.getenv("COGNITO_APP_CLIENT_ID"),
            verify_jwt_signature=_as_bool(
                os.getenv("AGENT_VERIFY_JWT_SIGNATURE"),
                default=True,
            ),
        )
