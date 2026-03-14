from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx


DEFAULT_TRANSCRIPTS = [
    {
        "name": "standing-desk-width",
        "turns": [
            "Compare standing desks with cable management and a width above 55 inches.",
        ],
    },
    {
        "name": "ergonomic-chair-budget",
        "turns": [
            "Find an ergonomic office chair under $150 with 4+ stars and fast delivery.",
            "Yes, do it.",
        ],
    },
]


@dataclass(slots=True)
class ReplayTurn:
    turn_index: int
    user_message: str
    status: str
    reply: str
    decision_summary: str
    score_breakdown: dict[str, Any]
    decision_diagnostics: dict[str, Any]
    source_health: dict[str, Any]
    blockers: list[str]
    missing_evidence: list[str]
    selected_candidate: dict[str, Any] | None


@dataclass(slots=True)
class ReplaySession:
    name: str
    session_id: str
    turns: list[ReplayTurn]


def _make_dev_token(sub: str = "replay-user", email: str = "replay@example.com") -> str:
    payload = {"sub": sub, "email": email, "exp": int(time.time()) + 3600}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    return f"header.{encoded}.sig"


def _load_transcripts(path: str | None) -> list[dict[str, Any]]:
    if not path:
        return DEFAULT_TRANSCRIPTS
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Transcript file must be a JSON array.")
    loaded: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Transcript entry {index} must be an object.")
        turns = item.get("turns")
        if not isinstance(turns, list) or not turns:
            raise ValueError(f"Transcript entry {index} is missing a non-empty 'turns' list.")
        loaded.append(
            {
                "name": str(item.get("name") or f"transcript-{index}"),
                "turns": [str(turn).strip() for turn in turns if str(turn).strip()],
            }
        )
    return loaded


async def _run_transcript(
    client: httpx.AsyncClient,
    *,
    api_base: str,
    headers: dict[str, str],
    name: str,
    turns: list[str],
) -> ReplaySession:
    created = await client.post(f"{api_base}/v1/sessions", headers=headers, timeout=30)
    created.raise_for_status()
    session_id = str(created.json()["sessionId"])
    replay_turns: list[ReplayTurn] = []

    for turn_index, message in enumerate(turns, start=1):
        response = await client.post(
            f"{api_base}/v1/chat",
            headers=headers,
            json={"sessionId": session_id, "message": message},
            timeout=240,
        )
        response.raise_for_status()
        payload = response.json()

        recommendation_response = await client.get(
            f"{api_base}/v1/recommendations/{session_id}",
            headers=headers,
            timeout=60,
        )
        recommendation_payload = recommendation_response.json() if recommendation_response.status_code == 200 else {}

        products_response = await client.get(
            f"{api_base}/v1/sessions/{session_id}/products",
            headers=headers,
            timeout=60,
        )
        products_payload = products_response.json() if products_response.status_code == 200 else {"items": []}
        items = products_payload.get("items", []) if isinstance(products_payload, dict) else []
        selected_candidate = items[0] if items and isinstance(items[0], dict) else None

        replay_turns.append(
            ReplayTurn(
                turn_index=turn_index,
                user_message=message,
                status=str(payload.get("status") or "unknown"),
                reply=str(payload.get("reply") or ""),
                decision_summary=str(
                    recommendation_payload.get("decisionSummary")
                    or payload.get("decisionSummary")
                    or ""
                ),
                score_breakdown=dict(
                    recommendation_payload.get("scoreBreakdown")
                    or payload.get("scoreBreakdown")
                    or {}
                ),
                decision_diagnostics=dict(
                    recommendation_payload.get("decisionDiagnostics")
                    or payload.get("decisionDiagnostics")
                    or {}
                ),
                source_health=dict(
                    recommendation_payload.get("sourceHealth")
                    or payload.get("sourceHealth")
                    or {}
                ),
                blockers=[str(item) for item in (payload.get("blockingAgents") or [])],
                missing_evidence=[str(item) for item in (payload.get("missingEvidence") or [])],
                selected_candidate=selected_candidate,
            )
        )

    return ReplaySession(name=name, session_id=session_id, turns=replay_turns)


def _print_session(session: ReplaySession) -> None:
    print(f"\n== {session.name} ==")
    print(f"session_id={session.session_id}")
    for turn in session.turns:
        print(f"\n[{turn.turn_index}] user={turn.user_message}")
        print(f"status={turn.status}")
        print(f"reply={turn.reply}")
        print(f"decisionSummary={turn.decision_summary}")
        print(f"scoreBreakdown={json.dumps(turn.score_breakdown, sort_keys=True)}")
        print(f"blockers={turn.blockers}")
        print(f"missingEvidence={turn.missing_evidence}")
        print(f"sourceHealth={json.dumps(turn.source_health, sort_keys=True)}")
        diagnostics = {
            "inputCounts": turn.decision_diagnostics.get("inputCounts"),
            "acceptedRejected": turn.decision_diagnostics.get("acceptedRejected"),
            "rejectionReasons": turn.decision_diagnostics.get("rejectionReasons"),
            "scoreContribution": turn.decision_diagnostics.get("scoreContribution"),
        }
        print(f"decisionDiagnostics={json.dumps(diagnostics, sort_keys=True)}")
        if turn.selected_candidate:
            selected = {
                "title": turn.selected_candidate.get("title"),
                "price": turn.selected_candidate.get("price"),
                "rating": turn.selected_candidate.get("rating"),
                "source": turn.selected_candidate.get("source"),
                "constraintTier": turn.selected_candidate.get("constraintTier"),
            }
            print(f"selectedCandidate={json.dumps(selected, sort_keys=True)}")
        else:
            print("selectedCandidate=null")


async def _main(args: argparse.Namespace) -> int:
    transcripts = _load_transcripts(args.transcript_file)
    token = args.bearer_token or _make_dev_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    api_base = args.api_base.rstrip("/")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        sessions = []
        for transcript in transcripts:
            session = await _run_transcript(
                client,
                api_base=api_base,
                headers=headers,
                name=str(transcript["name"]),
                turns=[str(turn) for turn in transcript["turns"]],
            )
            sessions.append(session)

    for session in sessions:
        _print_session(session)

    if args.output:
        serialized = [
            {
                "name": session.name,
                "sessionId": session.session_id,
                "turns": [asdict(turn) for turn in session.turns],
            }
            for session in sessions
        ]
        Path(args.output).write_text(json.dumps(serialized, indent=2), encoding="utf-8")
        print(f"\nWrote replay log to {args.output}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay real shopping transcripts for score calibration.")
    parser.add_argument("--api-base", default="http://localhost:8000", help="Backend API base URL.")
    parser.add_argument("--bearer-token", default="", help="Optional bearer token. Uses a generated dev token by default.")
    parser.add_argument("--transcript-file", default="", help="Optional JSON file with replay transcripts.")
    parser.add_argument("--output", default="", help="Optional JSON output path for replay logs.")
    args = parser.parse_args()

    try:
        code = asyncio.run(_main(args))
    except (httpx.HTTPError, ValueError, OSError) as exc:
        print(f"REPLAY RESULT: FAIL ({exc})")
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
