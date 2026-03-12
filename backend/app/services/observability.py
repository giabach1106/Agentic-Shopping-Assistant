from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RuntimeMetric:
    calls: int = 0
    fallback_calls: int = 0
    total_latency_seconds: float = 0.0
    estimated_cost_usd: float = 0.0


class RuntimeTelemetry:
    def __init__(self) -> None:
        self._by_task: dict[str, RuntimeMetric] = defaultdict(RuntimeMetric)
        self._by_session_calls: dict[str, int] = defaultdict(int)
        self._by_session_cost: dict[str, float] = defaultdict(float)

    def record(
        self,
        task_type: str,
        session_id: str,
        latency_seconds: float,
        fallback_used: bool,
        estimated_cost_usd: float,
    ) -> None:
        metric = self._by_task[task_type]
        metric.calls += 1
        metric.fallback_calls += int(fallback_used)
        metric.total_latency_seconds += latency_seconds
        metric.estimated_cost_usd += estimated_cost_usd

        self._by_session_calls[session_id] += 1
        self._by_session_cost[session_id] += estimated_cost_usd

    def session_usage(self, session_id: str) -> dict[str, Any]:
        calls = self._by_session_calls.get(session_id, 0)
        cost = self._by_session_cost.get(session_id, 0.0)
        return {"calls": calls, "estimatedCostUsd": round(cost, 5)}

    def snapshot(self) -> dict[str, Any]:
        tasks: dict[str, Any] = {}
        for task, metric in self._by_task.items():
            avg_latency = 0.0
            if metric.calls > 0:
                avg_latency = metric.total_latency_seconds / metric.calls
            tasks[task] = {
                "calls": metric.calls,
                "fallbackCalls": metric.fallback_calls,
                "avgLatencySeconds": round(avg_latency, 4),
                "estimatedCostUsd": round(metric.estimated_cost_usd, 5),
            }

        total_calls = sum(item.calls for item in self._by_task.values())
        total_fallback = sum(item.fallback_calls for item in self._by_task.values())
        total_cost = sum(item.estimated_cost_usd for item in self._by_task.values())

        return {
            "totalCalls": total_calls,
            "totalFallbackCalls": total_fallback,
            "totalEstimatedCostUsd": round(total_cost, 5),
            "tasks": tasks,
            "sessionsTracked": len(self._by_session_calls),
        }

