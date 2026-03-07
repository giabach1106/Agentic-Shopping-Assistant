from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    app_name: str
    sqlite_path: Path
    redis_url: str
    redis_key_prefix: str
    aws_region: str
    default_model_id: str
    fallback_model_id: str
    model_timeout_seconds: float
    latency_threshold_seconds: float
    max_retries: int
    mock_model: bool

    @classmethod
    def from_env(cls) -> "Settings":
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
            max_retries=int(os.getenv("MODEL_MAX_RETRIES", "2")),
            mock_model=_as_bool(os.getenv("MOCK_MODEL"), default=True),
        )

