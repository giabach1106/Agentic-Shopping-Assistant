"""Realtime evidence collectors for product/review/visual pipelines."""

from app.collectors.base import (
    CollectionResult,
    ProductCandidateData,
    RealtimeCollector,
    ReviewRecord,
    VisualRecord,
)
from app.collectors.realtime import build_realtime_collector

__all__ = [
    "CollectionResult",
    "ProductCandidateData",
    "RealtimeCollector",
    "ReviewRecord",
    "VisualRecord",
    "build_realtime_collector",
]
