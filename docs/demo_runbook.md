# Demo Runbook - AgentCart Supplements Lane

## 1. Start services

### Docker

```bash
docker compose up --build
```

### Local

Backend:

```bash
python -m pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## 2. Verify health

- Backend health: `http://localhost:8000/health`
- Frontend: `http://localhost:3000`
- Catalog metrics: `http://localhost:8000/v1/metrics/catalog` (requires auth token)

## 3. Warm up DB-first catalog before demo (recommended)

```bash
cd backend
python scripts/warmup_supplements_catalog.py --target 100
```

This seeds supplements catalog data used by the coverage auditor before fresh crawl.

## 4. Recommended demo prompt

```text
Find a whey isolate under $90 with third-party testing, low lactose, and no sucralose.
```

## 5. Live demo flow

1. Login with Cognito on the landing page.
2. Submit the whey prompt.
3. On `/results`, show:
   - minimal landing-to-session transition
   - verdict card
   - trust score, source coverage, and evidence freshness
   - agent response panel
    - session-bound follow-up chat
   - trust radar, source mix, and ABSA charts
   - ranked evidence ledger with promo/quality signals
    - shortlist cards with ingredient score
4. Open the top candidate product detail page.
5. Show:
   - trust radar chart
   - ingredient signal chart
   - evidence coverage chart
   - beneficial signals vs red flags
   - source links and trace timeline
6. Return to `/history` and reopen the same session to prove persistence.

## 6. Talking points for judges

- The system is session-first: history, chat, decision, and product detail stay tied to one `sessionId`.
- The backend now uses a DB-first evidence gate and only crawls when cache coverage is insufficient.
- The supplements lane is stronger than generic shopping because it explains ingredient quality, not just price and stars.
- The UI does not expose raw chain-of-thought. It shows structured reasoning, blockers, metrics, and evidence links.
- Checkout automation is intentionally constrained to a stop-before-payment handoff.
- Auth is strict in the main flow: login is required before session/chat/history APIs.

## 7. Backup script if data is incomplete

If the first run returns `NEED_DATA`:
- use the chat sidebar to add one clarifying message
- mention preferred sweetener policy or protein source
- resume the same run instead of starting a new search

## 8. Fallback safe path

If evidence is weak or conflicting:
- highlight the `WAIT` or `AVOID` verdict
- show the risk flags
- explain that the system prefers no recommendation over an overconfident recommendation
