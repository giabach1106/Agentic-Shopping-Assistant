from __future__ import annotations

import argparse
import json

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run end-to-end API walkthrough.")
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Backend API base URL.",
    )
    return parser.parse_args()


def _pretty(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=True)


def main() -> None:
    args = parse_args()
    with httpx.Client(timeout=30.0) as client:
        print("1) Creating session...")
        created = client.post(f"{args.base_url}/v1/sessions")
        created.raise_for_status()
        session_id = created.json()["sessionId"]
        print(f"Session ID: {session_id}")

        print("\n2) First chat turn (missing fields expected)...")
        first_turn = client.post(
            f"{args.base_url}/v1/chat",
            json={"sessionId": session_id, "message": "I need a chair for my dorm"},
        )
        first_turn.raise_for_status()
        print(_pretty(first_turn.json()))

        print("\n3) Resume run with follow-up details...")
        resume = client.post(
            f"{args.base_url}/v1/runs/{session_id}/resume",
            json={
                "message": (
                    "under $150, 4+ stars, delivered by Friday, "
                    "autofill checkout details, uploaded photo from my room"
                )
            },
        )
        resume.raise_for_status()
        print(_pretty(resume.json()))

        print("\n4) Fetch recommendation payload...")
        recommendation = client.get(f"{args.base_url}/v1/recommendations/{session_id}")
        recommendation.raise_for_status()
        print(_pretty(recommendation.json()))

        print("\n5) Snapshot for traceability...")
        snapshot = client.get(f"{args.base_url}/v1/sessions/{session_id}")
        snapshot.raise_for_status()
        print(_pretty(snapshot.json()))


if __name__ == "__main__":
    main()

