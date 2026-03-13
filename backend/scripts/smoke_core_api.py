from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(slots=True)
class FlowResult:
    session_id: str
    status: str
    reply: str
    coverage_audit: dict[str, Any]
    product_count: int
    rated_ratio: float
    noisy_titles: list[str]


def _make_dev_token(sub: str = "smoke-user", email: str = "smoke@example.com") -> str:
    payload = {"sub": sub, "email": email, "exp": int(time.time()) + 3600}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    return f"header.{encoded}.sig"


def _is_noisy_title(value: str) -> bool:
    title = re.sub(r"\s+", " ", value).strip().lower()
    return bool(
        re.fullmatch(r"[0-9][0-9,]*\s+ratings?", title)
        or title.startswith("options:")
        or title in {"ratings", "global ratings"}
    )


async def _run_flow(
    client: httpx.AsyncClient,
    api_base: str,
    headers: dict[str, str],
    prompt: str,
    follow_ups: list[str],
) -> FlowResult:
    created = await client.post(f"{api_base}/v1/sessions", headers=headers, timeout=30)
    created.raise_for_status()
    session_id = str(created.json()["sessionId"])

    status = "NEED_DATA"
    reply = ""
    coverage_audit: dict[str, Any] = {}

    for message in [prompt, *follow_ups]:
        chat = await client.post(
            f"{api_base}/v1/chat",
            headers=headers,
            json={"sessionId": session_id, "message": message},
            timeout=180,
        )
        chat.raise_for_status()
        payload = chat.json()
        status = str(payload.get("status") or "ERROR")
        reply = str(payload.get("reply") or "")
        coverage_audit = dict(payload.get("coverageAudit") or {})
        if status != "NEED_DATA":
            break

    products_response = await client.get(
        f"{api_base}/v1/sessions/{session_id}/products",
        headers=headers,
        timeout=30,
    )
    products_payload = products_response.json() if products_response.status_code == 200 else {"items": []}
    items = products_payload.get("items", []) if isinstance(products_payload, dict) else []
    product_count = len(items)

    rated_products = 0
    noisy_titles: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if title and _is_noisy_title(title):
            noisy_titles.append(title)
        rating_coverage = dict(item.get("ratingCoverage") or {})
        if int(rating_coverage.get("ratedOfferCount") or 0) > 0:
            rated_products += 1
    rated_ratio = round((rated_products / product_count), 4) if product_count > 0 else 0.0

    return FlowResult(
        session_id=session_id,
        status=status,
        reply=reply,
        coverage_audit=coverage_audit,
        product_count=product_count,
        rated_ratio=rated_ratio,
        noisy_titles=noisy_titles,
    )


async def _main(args: argparse.Namespace) -> int:
    token = args.bearer_token or _make_dev_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    api_base = args.api_base.rstrip("/")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        flows = [
            (
                "Whey isolate under $100, low lactose, 4+ star",
                ["this friday"],
            ),
            (
                "Find a whey protein isolate under $90 with third-party testing and low lactose.",
                ["4 stars", "in 6 days"],
            ),
        ]
        results = []
        for prompt, follow_ups in flows:
            result = await _run_flow(client, api_base, headers, prompt, follow_ups)
            results.append(result)

    print("Core API smoke results")
    print("----------------------")
    hard_fail = False
    for idx, result in enumerate(results, start=1):
        print(f"[Flow {idx}] session={result.session_id}")
        print(f"  status={result.status}")
        print(f"  reply={result.reply}")
        print(
            "  coverage="
            + json.dumps(
                {
                    "sourceCoverage": result.coverage_audit.get("sourceCoverage"),
                    "commerceSourceCoverage": result.coverage_audit.get("commerceSourceCoverage"),
                    "ratingCount": result.coverage_audit.get("ratingCount"),
                    "ratedCoverageRatio": result.coverage_audit.get("ratedCoverageRatio"),
                    "blockedCommerceSources": result.coverage_audit.get("blockedCommerceSources"),
                }
            )
        )
        print(f"  products={result.product_count}, ratedRatio={result.rated_ratio}")
        if result.noisy_titles:
            print(f"  noisyTitles={result.noisy_titles[:3]}")

        if result.product_count < 10:
            hard_fail = True
        if result.rated_ratio < 0.6:
            hard_fail = True
        if result.noisy_titles:
            hard_fail = True

    if hard_fail:
        print("SMOKE RESULT: FAIL")
        return 1
    print("SMOKE RESULT: PASS")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Core API smoke test for crawl/data integrity.")
    parser.add_argument("--api-base", default="http://localhost:8000", help="Backend API base URL.")
    parser.add_argument("--bearer-token", default="", help="Optional bearer token. Uses generated dev token by default.")
    args = parser.parse_args()

    try:
        import asyncio

        code = asyncio.run(_main(args))
    except httpx.HTTPError as exc:
        print(f"SMOKE RESULT: FAIL ({exc})")
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
