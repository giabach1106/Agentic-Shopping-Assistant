from __future__ import annotations

import argparse

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
    return parser.parse_args()


def ensure_session(client: httpx.Client, base_url: str, session_id: str | None) -> str:
    if session_id:
        return session_id

    response = client.post(f"{base_url}/v1/sessions")
    response.raise_for_status()
    created = response.json()
    return created["sessionId"]


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


if __name__ == "__main__":
    main()

