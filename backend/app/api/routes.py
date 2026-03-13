from __future__ import annotations

import base64
import re
import hashlib
import json
import time
from collections import defaultdict
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from app.core.container import ServiceContainer
from app.models.schemas import (
    CatalogMetricsResponse,
    ChatRequest,
    ChatResponse,
    CreateSessionResponse,
    HealthResponse,
    RecommendationResponse,
    RuntimeMetricsResponse,
    ResumeRunRequest,
    SessionListResponse,
    SessionProductsEnvelopeResponse,
    SessionSnapshotResponse,
    VoiceConsultRequest,
    VoiceConsultResponse,
)
from app.orchestrator.message_formatter import build_assistant_meta

router = APIRouter()


def _services(request: Request) -> ServiceContainer:
    return request.app.state.services


def _decode_token_claims(authorization: str | None) -> dict[str, Any]:
    if not authorization:
        return {}
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return {}
    token = parts[1]
    payload = token.split(".")
    if len(payload) < 2:
        return {}
    encoded = payload[1] + "=" * (-len(payload[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(encoded.encode("utf-8"))
        loaded = json.loads(decoded.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _require_token_claims(request: Request) -> dict[str, Any]:
    services = _services(request)
    claims = _decode_token_claims(request.headers.get("Authorization"))
    if not services.settings.require_auth:
        return claims
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token.",
        )
    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing required subject claim.",
        )
    expires_at = claims.get("exp")
    if isinstance(expires_at, (int, float)) and int(expires_at) <= int(time.time()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
        )
    return claims


def _product_id(source_url: str, evidence_refs: list[str]) -> str:
    seed = evidence_refs[0] if evidence_refs else source_url
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def _normalize_url(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        return ""
    parsed = urlparse(trimmed)
    normalized = parsed._replace(query="", fragment="")
    path = re.sub(r"/ref=.*$", "", normalized.path).rstrip("/")
    normalized = normalized._replace(path=path or "/")
    return normalized.geturl()


def _store_name_from_url(value: str) -> str:
    host = urlparse(value).netloc.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    if host:
        return host.split(":")[0]
    return "Marketplace"


def _is_search_listing_url(value: str) -> bool:
    lower = value.lower()
    return ("/search?" in lower) or ("/sch/i.html" in lower)


def _canonical_title_signature(value: str) -> str:
    tokens = [
        token
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if len(token) >= 3 and token not in {"with", "from", "under", "over", "for"}
    ]
    if not tokens:
        return ""
    return " ".join(tokens[:8])


def _canonical_product_key(title: str, source_url: str) -> str:
    signature = _canonical_title_signature(title)
    normalized_url = _normalize_url(source_url)
    return signature or normalized_url


def _source_priority(source: str) -> int:
    mapping = {"amazon": 0, "walmart": 1, "ebay": 2}
    return mapping.get(source.lower(), 99)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _offer_sort_key(offer: dict[str, Any]) -> tuple[int, int, int, float, float]:
    rating_count = _safe_int(offer.get("ratingCount"), 0)
    rating_value = _safe_float(offer.get("rating"), 0.0)
    return (
        _source_priority(str(offer.get("source") or "")),
        0 if rating_count > 0 else 1,
        -rating_count,
        -rating_value,
        _safe_float(offer.get("price"), 999999.0),
    )


def _build_session_products(checkpoint: dict[str, Any], services: ServiceContainer) -> dict[str, Any]:
    agent_outputs = dict(checkpoint.get("agent_outputs") or {})
    collection = dict(checkpoint.get("collection") or {})
    price = dict(agent_outputs.get("price") or {})
    review = dict(agent_outputs.get("review") or {})
    decision_block = dict(agent_outputs.get("decision") or {})
    review_texts = [
        str(item.get("review_text") or "")
        for item in collection.get("reviews", [])
        if isinstance(item, dict) and str(item.get("review_text") or "").strip()
    ]
    collect_lookup: dict[str, dict[str, Any]] = {}
    offers_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in collection.get("products", []):
        if not isinstance(item, dict):
            continue
        url = _normalize_url(str(item.get("url") or ""))
        if url:
            collect_lookup[url] = item
        if not url.startswith("http") or _is_search_listing_url(url):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        price_value = _safe_float(item.get("price"), 0.0)
        if price_value <= 0:
            continue
        source_name = str(item.get("source") or "").strip().lower() or _store_name_from_url(url)
        rating_value = _safe_float(item.get("avg_rating") or item.get("rating"), 0.0)
        rating_count = _safe_int(item.get("rating_count") or item.get("ratingCount"), 0)
        offer = {
            "source": source_name,
            "storeName": str(item.get("seller_info") or "").strip() or source_name,
            "sourceUrl": url,
            "price": price_value,
            "rating": rating_value if rating_value > 0 else None,
            "ratingCount": rating_count,
            "shippingETA": str(item.get("shipping_eta") or "unknown"),
            "returnPolicy": str(item.get("return_policy") or "unknown"),
            "imageUrl": str(item.get("image_url") or item.get("imageUrl") or "").strip() or None,
        }
        canonical_key = _canonical_product_key(title, url)
        if canonical_key:
            offers_by_key[canonical_key].append(offer)

    visual_lookup: dict[str, str] = {}
    for item in collection.get("visuals", []):
        if not isinstance(item, dict):
            continue
        url = _normalize_url(str(item.get("url") or ""))
        image_url = str(item.get("image_url") or item.get("imageUrl") or "").strip()
        if url and image_url and url not in visual_lookup:
            visual_lookup[url] = image_url

    items: list[dict[str, Any]] = []
    seen_canonical_ids: set[str] = set()
    for candidate in price.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        source_url = str(candidate.get("sourceUrl") or "").strip()
        normalized_source_url = _normalize_url(source_url)
        if not normalized_source_url.startswith("http") or _is_search_listing_url(normalized_source_url):
            continue
        title = str(candidate.get("title") or "").strip()
        if not title:
            continue
        canonical_key = _canonical_product_key(title, normalized_source_url)
        canonical_product_id = hashlib.sha1(canonical_key.encode("utf-8")).hexdigest()[:16]
        if canonical_product_id in seen_canonical_ids:
            continue
        seen_canonical_ids.add(canonical_product_id)
        collect_item = collect_lookup.get(normalized_source_url, {})
        evidence_refs = [
            str(item).strip()
            for item in candidate.get("evidenceRefs", [])
            if str(item).strip()
        ]
        analysis = services.ingredient_analyzer.analyze(
            title=title,
            description=" ".join(str(item) for item in review.get("pros", [])[:2]),
            review_texts=review_texts,
            evidence_refs=evidence_refs,
            source_url=normalized_source_url,
        )
        source_name = str(collect_item.get("source") or "").strip().lower() or _store_name_from_url(normalized_source_url)
        store_name = (
            str(collect_item.get("seller_info") or "").strip()
            or source_name
            or _store_name_from_url(normalized_source_url)
        )
        image_url = str(
            collect_item.get("image_url")
            or collect_item.get("imageUrl")
            or visual_lookup.get(normalized_source_url, "")
        ).strip()
        candidate_rating = _safe_float(candidate.get("rating"), 0.0)
        primary_offer = {
            "source": source_name,
            "storeName": store_name,
            "sourceUrl": normalized_source_url,
            "price": _safe_float(candidate.get("price"), 0.0),
            "rating": candidate_rating if candidate_rating > 0 else None,
            "ratingCount": _safe_int(collect_item.get("rating_count") or collect_item.get("ratingCount"), 0),
            "shippingETA": str(candidate.get("shippingETA") or "unknown"),
            "returnPolicy": str(candidate.get("returnPolicy") or "unknown"),
            "imageUrl": image_url or None,
        }
        offer_by_url: dict[str, dict[str, Any]] = {}
        for offer in [primary_offer, *offers_by_key.get(canonical_key, [])]:
            offer_url = _normalize_url(str(offer.get("sourceUrl") or ""))
            if not offer_url:
                continue
            if _is_search_listing_url(offer_url):
                continue
            offer["sourceUrl"] = offer_url
            existing_offer = offer_by_url.get(offer_url)
            if existing_offer is None:
                offer_by_url[offer_url] = offer
                continue
            existing_rating_count = _safe_int(existing_offer.get("ratingCount"), 0)
            next_rating_count = _safe_int(offer.get("ratingCount"), 0)
            existing_rating = _safe_float(existing_offer.get("rating"), 0.0)
            next_rating = _safe_float(offer.get("rating"), 0.0)
            if (
                next_rating_count > existing_rating_count
                or (next_rating_count == existing_rating_count and next_rating > existing_rating)
            ):
                merged = dict(existing_offer)
                merged.update(offer)
                offer_by_url[offer_url] = merged
            elif not existing_offer.get("imageUrl") and offer.get("imageUrl"):
                existing_offer["imageUrl"] = offer["imageUrl"]

        merged_offers = list(offer_by_url.values())
        merged_offers.sort(key=_offer_sort_key)
        primary_offer = (
            next(
                (offer for offer in merged_offers if offer.get("sourceUrl") == normalized_source_url),
                None,
            )
            or (merged_offers[0] if merged_offers else primary_offer)
        )
        if merged_offers and primary_offer in merged_offers:
            merged_offers = [primary_offer, *[item for item in merged_offers if item is not primary_offer]]
        source_breakdown_counter: dict[str, int] = {}
        for offer in merged_offers:
            source = str(offer.get("source") or "unknown")
            source_breakdown_counter[source] = source_breakdown_counter.get(source, 0) + 1
        rated_offer_count = sum(
            1
            for offer in merged_offers
            if (_safe_float(offer.get("rating"), 0.0) > 0)
            or (_safe_int(offer.get("ratingCount"), 0) > 0)
        )
        total_offer_count = len(merged_offers)
        unique_refs: list[str] = []
        for ref in evidence_refs:
            if ref and ref not in unique_refs:
                unique_refs.append(ref)
        items.append(
            {
                "productId": _product_id(canonical_key, unique_refs),
                "canonicalProductId": canonical_product_id,
                "title": title,
                "storeName": str(primary_offer.get("storeName") or store_name),
                "source": str(primary_offer.get("source") or source_name),
                "sourceUrl": str(primary_offer.get("sourceUrl") or normalized_source_url),
                "imageUrl": primary_offer.get("imageUrl") or None,
                "price": _safe_float(primary_offer.get("price"), 0.0),
                "rating": (
                    _safe_float(primary_offer.get("rating"), 0.0)
                    if _safe_float(primary_offer.get("rating"), 0.0) > 0
                    else None
                ),
                "shippingETA": str(primary_offer.get("shippingETA") or "unknown"),
                "returnPolicy": str(primary_offer.get("returnPolicy") or "unknown"),
                "checkoutReady": candidate.get("checkoutReady", False),
                "evidenceRefs": unique_refs,
                "primaryOffer": primary_offer,
                "offers": merged_offers,
                "sourceBreakdown": [
                    {"source": source, "count": count}
                    for source, count in sorted(
                        source_breakdown_counter.items(),
                        key=lambda entry: (_source_priority(entry[0]), -entry[1], entry[0]),
                    )
                ],
                "ratingCoverage": {
                    "ratedOfferCount": rated_offer_count,
                    "totalOfferCount": total_offer_count,
                },
                "pros": [str(item) for item in review.get("pros", [])[:4]],
                "cons": [str(item) for item in review.get("cons", [])[:4]],
                "ingredientAnalysis": analysis,
                "scientificScore": decision_block.get("scientificScore", {}),
                "evidenceStats": decision_block.get("evidenceStats", {}),
                "trace": decision_block.get("trace", []),
            }
        )

    return {"sessionId": checkpoint.get("session_id"), "items": items}


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    services = _services(request)
    return HealthResponse(
        status="ok",
        app=services.settings.app_name,
        checkpointBackend=services.session_service.checkpoint_backend,
        defaultModel=services.settings.default_model_id,
        fallbackModel=services.settings.fallback_model_id,
    )


@router.get("/v1/metrics/runtime", response_model=RuntimeMetricsResponse)
async def runtime_metrics(request: Request) -> RuntimeMetricsResponse:
    _require_token_claims(request)
    services = _services(request)
    snapshot = services.model_router.snapshot_metrics()
    return RuntimeMetricsResponse(**snapshot)


@router.get("/v1/metrics/catalog", response_model=CatalogMetricsResponse)
async def catalog_metrics(request: Request) -> CatalogMetricsResponse:
    _require_token_claims(request)
    services = _services(request)
    payload = await services.session_service.evidence_store.catalog_metrics()
    return CatalogMetricsResponse(**payload)


@router.options("/v1/sessions", status_code=status.HTTP_204_NO_CONTENT)
async def options_sessions() -> Response:
    # Explicit OPTIONS handler keeps browser preflight behavior stable across environments.
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/v1/sessions",
    response_model=CreateSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(request: Request) -> CreateSessionResponse:
    services = _services(request)
    claims = _require_token_claims(request)
    created = await services.session_service.create_session(
        user_sub=str(claims.get("sub") or "").strip() or None,
        user_email=str(claims.get("email") or "").strip() or None,
    )
    return CreateSessionResponse(**created)


@router.get("/v1/sessions", response_model=SessionListResponse)
async def list_sessions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None),
) -> SessionListResponse:
    services = _services(request)
    claims = _require_token_claims(request)
    result = await services.session_service.list_sessions(
        limit=limit,
        cursor=cursor,
        user_sub=str(claims.get("sub") or "").strip() or None,
    )
    return SessionListResponse(**result)


@router.post("/v1/chat", response_model=ChatResponse)
async def chat(request: Request, payload: ChatRequest) -> ChatResponse:
    services = _services(request)
    claims = _require_token_claims(request)
    user_sub = str(claims.get("sub") or "").strip() or None
    exists = await services.session_service.require_session(payload.session_id, user_sub)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{payload.session_id}' was not found.",
        )

    await services.session_service.add_user_message(payload.session_id, payload.message)
    history = await services.session_service.get_history(payload.session_id)
    previous_checkpoint = await services.session_service.get_checkpoint_state(
        payload.session_id
    )
    orchestration = await services.orchestrator.run_turn(
        session_id=payload.session_id,
        user_message=payload.message,
        history=history,
        previous_state=previous_checkpoint,
    )
    await services.session_service.add_assistant_message(
        payload.session_id,
        orchestration.reply,
        meta=build_assistant_meta(
            reply=orchestration.reply,
            decision=orchestration.decision,
            scientific_score=orchestration.scientific_score,
            missing_evidence=orchestration.missing_evidence,
            blocking_agents=orchestration.blocking_agents,
            trace=orchestration.trace,
        ),
    )
    await services.session_service.save_state(payload.session_id, orchestration.state)

    return ChatResponse(
        sessionId=payload.session_id,
        status=orchestration.status,
        reply=orchestration.reply,
        decision=orchestration.decision,
        scientificScore=orchestration.scientific_score,
        evidenceStats=orchestration.evidence_stats,
        coverageAudit=orchestration.coverage_audit,
        trace=orchestration.trace,
        missingEvidence=orchestration.missing_evidence,
        blockingAgents=orchestration.blocking_agents,
        state=orchestration.state,
    )


@router.post("/v1/runs/{session_id}/resume", response_model=ChatResponse)
async def resume_run(
    request: Request,
    session_id: str,
    payload: ResumeRunRequest,
) -> ChatResponse:
    services = _services(request)
    claims = _require_token_claims(request)
    user_sub = str(claims.get("sub") or "").strip() or None
    exists = await services.session_service.require_session(session_id, user_sub)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' was not found.",
        )

    previous_checkpoint = await services.session_service.get_checkpoint_state(session_id)
    if previous_checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No checkpoint state found for session '{session_id}'.",
        )

    if previous_checkpoint.get("needs_follow_up") and not payload.message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This run is waiting for follow-up input. "
                "Provide message in request body to resume."
            ),
        )

    user_message = payload.message or "continue with existing constraints"
    await services.session_service.add_user_message(session_id, user_message)
    history = await services.session_service.get_history(session_id)
    orchestration = await services.orchestrator.run_turn(
        session_id=session_id,
        user_message=user_message,
        history=history,
        previous_state=previous_checkpoint,
    )
    await services.session_service.add_assistant_message(
        session_id,
        orchestration.reply,
        meta=build_assistant_meta(
            reply=orchestration.reply,
            decision=orchestration.decision,
            scientific_score=orchestration.scientific_score,
            missing_evidence=orchestration.missing_evidence,
            blocking_agents=orchestration.blocking_agents,
            trace=orchestration.trace,
        ),
    )
    await services.session_service.save_state(session_id, orchestration.state)

    return ChatResponse(
        sessionId=session_id,
        status=orchestration.status,
        reply=orchestration.reply,
        decision=orchestration.decision,
        scientificScore=orchestration.scientific_score,
        evidenceStats=orchestration.evidence_stats,
        coverageAudit=orchestration.coverage_audit,
        trace=orchestration.trace,
        missingEvidence=orchestration.missing_evidence,
        blockingAgents=orchestration.blocking_agents,
        state=orchestration.state,
    )


@router.get("/v1/sessions/{session_id}", response_model=SessionSnapshotResponse)
async def get_session(request: Request, session_id: str) -> SessionSnapshotResponse:
    services = _services(request)
    claims = _require_token_claims(request)
    user_sub = str(claims.get("sub") or "").strip() or None
    exists = await services.session_service.require_session(session_id, user_sub)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' was not found.",
        )
    snapshot = await services.session_service.get_snapshot(session_id)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' was not found.",
        )
    return SessionSnapshotResponse(**snapshot)


@router.get("/v1/sessions/{session_id}/products", response_model=SessionProductsEnvelopeResponse)
async def get_session_products(
    request: Request,
    session_id: str,
) -> SessionProductsEnvelopeResponse:
    services = _services(request)
    claims = _require_token_claims(request)
    user_sub = str(claims.get("sub") or "").strip() or None
    exists = await services.session_service.require_session(session_id, user_sub)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' was not found.",
        )
    checkpoint = await services.session_service.get_checkpoint_state(session_id)
    if checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No product state found for session '{session_id}'.",
        )
    payload = _build_session_products(checkpoint, services)
    if not payload["items"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No product candidates available for session '{session_id}'.",
        )
    payload["sessionId"] = session_id
    return SessionProductsEnvelopeResponse(**payload)


@router.get(
    "/v1/recommendations/{session_id}",
    response_model=RecommendationResponse,
)
async def get_recommendation(
    request: Request,
    session_id: str,
) -> RecommendationResponse:
    services = _services(request)
    claims = _require_token_claims(request)
    user_sub = str(claims.get("sub") or "").strip() or None
    exists = await services.session_service.require_session(session_id, user_sub)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' was not found.",
        )
    checkpoint = await services.session_service.get_checkpoint_state(session_id)
    if checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No recommendation state found for session '{session_id}'.",
        )

    decision = (checkpoint.get("agent_outputs") or {}).get("decision")
    if not decision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision output is not available for session '{session_id}' yet.",
        )

    return RecommendationResponse(
        sessionId=session_id,
        status=decision.get("status", "ERROR"),
        decision=decision.get("decision"),
        scientificScore=decision.get("scientificScore", {}),
        evidenceStats=decision.get("evidenceStats", {}),
        coverageAudit=decision.get("coverageAudit", {}),
        trace=decision.get("trace", []),
        missingEvidence=decision.get("missingEvidence", []),
        blockingAgents=decision.get("blockingAgents", []),
    )


@router.post("/v1/voice/consult", response_model=VoiceConsultResponse)
async def voice_consult(
    request: Request,
    payload: VoiceConsultRequest,
) -> VoiceConsultResponse:
    services = _services(request)
    claims = _require_token_claims(request)
    user_sub = str(claims.get("sub") or "").strip() or None
    exists = await services.session_service.require_session(payload.session_id, user_sub)
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{payload.session_id}' was not found.",
        )

    checkpoint = await services.session_service.get_checkpoint_state(payload.session_id)
    if checkpoint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No checkpoint state found for session '{payload.session_id}'.",
        )

    decision = (checkpoint.get("agent_outputs") or {}).get("decision")
    if decision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision output is not available for session '{payload.session_id}'.",
        )

    recommendation = decision.get("decision", {})
    model_result = await services.model_router.call(
        task_type="voice_consultation",
        payload={
            "prompt": (
                "You are a concise shopping consultant. "
                f"Question: {payload.question}. "
                f"Current recommendation: verdict={recommendation.get('verdict')}, "
                f"trustScore={recommendation.get('finalTrust')}, "
                f"topReasons={recommendation.get('topReasons')}, "
                f"riskFlags={recommendation.get('riskFlags')}."
            )
        },
        session_id=payload.session_id,
    )

    answer = (
        f"[VoiceConsult] Status {decision.get('status')} "
        f"Verdict {recommendation.get('verdict')} "
        f"(Trust {recommendation.get('finalTrust')}): {model_result.output.get('text')}"
    )
    return VoiceConsultResponse(
        sessionId=payload.session_id,
        answer=answer,
        mode="text-simulated-voice",
        modelMeta={
            "modelId": model_result.model_id,
            "fallbackUsed": model_result.fallback_used,
            "fallbackReason": model_result.fallback_reason,
        },
    )
