from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import Settings


def build_project_profile(settings: Settings) -> dict[str, Any]:
    readme_path = Path(__file__).resolve().parents[3] / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    capabilities = _extract_bullets(readme_text, "Core capabilities")
    stack = _extract_bullets(readme_text, "Stack")
    endpoints = _extract_bullets(readme_text, "API endpoints used by frontend")

    return {
        "name": "AgentCart",
        "summary": (
            "Session-based shopping assistant with chat, evidence collection, "
            "explainable scoring, and follow-up workflow."
        ),
        "coreCapabilities": capabilities,
        "stack": stack,
        "apiEndpoints": endpoints,
        "runtime": {
            "runtimeMode": settings.runtime_mode,
            "ragBackend": settings.rag_backend,
            "uiExecutorBackend": settings.ui_executor_backend,
            "requireAuth": settings.require_auth,
            "stopBeforePay": settings.stop_before_pay,
            "mockModel": settings.mock_model,
        },
        "enabledServices": [
            "LangGraph orchestration",
            "FastAPI backend",
            "Next.js frontend",
            "SQLite session/evidence store",
            "Redis checkpoint store",
            "Cognito auth" if settings.require_auth else "Anonymous mode",
            f"RAG: {settings.rag_backend}",
            f"UI executor: {settings.ui_executor_backend}",
        ],
    }


def _extract_bullets(markdown: str, heading: str) -> list[str]:
    if not markdown:
        return []
    start_marker = f"## {heading}"
    start = markdown.find(start_marker)
    if start < 0:
        return []
    remainder = markdown[start + len(start_marker) :]
    next_heading = remainder.find("\n## ")
    section = remainder if next_heading < 0 else remainder[:next_heading]
    bullets: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    return bullets
