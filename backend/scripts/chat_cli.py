from __future__ import annotations

import argparse
import json
from typing import Any

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Terminal chat client for agent core.")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Backend API base URL.",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Existing session ID. If omitted, a new session will be created.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-agent execution trace from response state.",
    )
    parser.add_argument(
        "--raw-state",
        action="store_true",
        help="Print full JSON state (implies --verbose).",
    )
    return parser.parse_args()


def ensure_session(client: httpx.Client, base_url: str, session_id: str | None) -> str:
    if session_id:
        return session_id

    response = client.post(f"{base_url}/v1/sessions")
    response.raise_for_status()
    created = response.json()
    return created["sessionId"]


def _print_model_meta(agent_name: str, payload: dict[str, Any]) -> None:
    model_meta = payload.get("modelMeta")
    if not isinstance(model_meta, dict):
        return
    model_id = model_meta.get("modelId")
    fallback_used = model_meta.get("fallbackUsed")
    fallback_reason = model_meta.get("fallbackReason")
    print(
        f"trace> {agent_name}.model={model_id} "
        f"fallbackUsed={fallback_used} "
        f"fallbackReason={fallback_reason}"
    )


def print_trace(payload: dict[str, Any], raw_state: bool) -> None:
    state = payload.get("state")
    if not isinstance(state, dict):
        return

    if raw_state:
        print("trace> full state:")
        print(json.dumps(state, ensure_ascii=True, indent=2))
        return

    print("trace> state summary:")
    print(
        "trace> followUp="
        f"{state.get('needs_follow_up')} "
        f"followUpCount={state.get('follow_up_count')}"
    )

    outputs = state.get("agent_outputs")
    if not isinstance(outputs, dict):
        return

    planner = outputs.get("planner")
    if isinstance(planner, dict):
        constraints = planner.get("constraints") or {}
        if isinstance(constraints, dict):
            print(
                "trace> planner.constraints "
                f"category={constraints.get('category')} "
                f"budgetMax={constraints.get('budgetMax')} "
                f"minRating={constraints.get('minRating')} "
                f"deliveryDeadline={constraints.get('deliveryDeadline')}"
            )
        print(
            "trace> planner.missingFields="
            f"{planner.get('missingFields', [])} "
            f"followUpQuestion={planner.get('followUpQuestion')}"
        )
        _print_model_meta("planner", planner)

    review = outputs.get("review")
    if isinstance(review, dict):
        evidence_refs = review.get("evidenceRefs", [])
        evidence_count = len(evidence_refs) if isinstance(evidence_refs, list) else 0
        print(
            "trace> review "
            f"confidence={review.get('confidence')} "
            f"paidPromoLikelihood={review.get('paidPromoLikelihood')} "
            f"evidenceRefs={evidence_count}"
        )
        _print_model_meta("review", review)

    visual = outputs.get("visual")
    if isinstance(visual, dict):
        print(
            "trace> visual "
            f"status={visual.get('status')} "
            f"authenticityScore={visual.get('authenticityScore')} "
            f"confidence={visual.get('confidence')}"
        )
        _print_model_meta("visual", visual)

    price = outputs.get("price")
    if isinstance(price, dict):
        candidates = price.get("candidates", [])
        blockers = price.get("blockers", [])
        candidate_count = len(candidates) if isinstance(candidates, list) else 0
        print(
            "trace> price "
            f"candidates={candidate_count} "
            f"blockers={blockers} "
            f"consentAutofill={price.get('consentAutofill')}"
        )
        _print_model_meta("price", price)

    decision = outputs.get("decision")
    if isinstance(decision, dict):
        decision_payload = decision.get("decision", {})
        scientific_score = decision.get("scientificScore", {})
        print(
            "trace> decision "
            f"status={decision.get('status')} "
            f"verdict={decision_payload.get('verdict')} "
            f"trustScore={decision_payload.get('finalTrust')} "
            f"ratingReliability={scientific_score.get('ratingReliability')}"
        )
        _print_model_meta("decision", decision)


def main() -> None:
    args = parse_args()
    with httpx.Client(timeout=30.0) as client:
        session_id = ensure_session(client, args.base_url, args.session_id)
        print(f"Session ID: {session_id}")
        print("Type your message. Use 'exit' or 'quit' to stop.")

        while True:
            user_input = input("> ").strip()
            if user_input.lower() in {"exit", "quit"}:
                break
            if not user_input:
                continue

            response = client.post(
                f"{args.base_url}/v1/chat",
                json={"sessionId": session_id, "message": user_input},
            )
            if response.status_code >= 400:
                print(f"[error {response.status_code}] {response.text}")
                continue

            payload = response.json()
            print(f"assistant> {payload['reply']}")
            if args.verbose or args.raw_state:
                print_trace(payload, raw_state=args.raw_state)


if __name__ == "__main__":
    main()
