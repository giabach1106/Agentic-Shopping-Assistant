# AgentCart

AgentCart is a session-bound shopping agent for hackathon demos where trust matters more than raw search speed.

This build is optimized for supplements and whey protein:
- DB-first evidence reuse before fresh crawl
- structured reasoning timeline instead of opaque output
- ingredient scoring with beneficial signals and red flags
- session history, product detail, charts, and evidence references in the UI
- dark/light theme support

## Stack

- Frontend: Next.js 15, React 19, Tailwind CSS 4, Recharts
- Backend: FastAPI, LangGraph orchestration, SQLite memory/evidence cache, Redis checkpoints
- Auth: Cognito on the frontend, token passthrough on the backend

## Core demo flow

1. User logs in with Cognito.
2. Frontend creates a session with `POST /v1/sessions`.
3. User prompt goes to `POST /v1/chat`.
4. Backend checks cached evidence first, then collects only when coverage is insufficient.
5. Coverage auditor checks cache + catalog before crawl.
6. UI renders:
   - verdict and trust score
   - scientific score radar, source-mix chart, and ABSA chart
   - structured trace timeline and ranked evidence table
   - shortlist of products from session state
   - product detail with ingredient charts and source links
7. Follow-up questions continue in the same session with `POST /v1/runs/{session_id}/resume`.

## Repository layout

- `frontend/`: Next.js app
- `backend/`: FastAPI app, agent orchestration, tests
- `docs/`: demo script and submission checklist

## Local setup

### 1. Backend env

Create root `.env` or export equivalent values:

```env
MOCK_MODEL=true
AWS_REGION=us-east-1
AGENT_SQLITE_PATH=backend/data/agent_memory.sqlite3
AGENT_REDIS_URL=redis://localhost:6379/0
AGENT_CORS_ALLOW_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
AGENT_REQUIRE_AUTH=true
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_COGNITO_DOMAIN=your-domain.auth.us-east-1.amazoncognito.com
NEXT_PUBLIC_COGNITO_CLIENT_ID=your-client-id
NEXT_PUBLIC_COGNITO_REDIRECT_URI=http://localhost:3000
```

Important:
- `NEXT_PUBLIC_*` values are consumed by the frontend.
- `AGENT_CORS_ALLOW_ORIGINS` must include the frontend origin or browser preflight will fail.
- `AGENT_REQUIRE_AUTH=true` enforces strict bearer auth for `/v1/*`.
- `MOCK_MODEL=true` is the easiest local demo mode.
- If Redis is unavailable, backend falls back to in-memory checkpoints.

### 2. Run backend

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux
# source .venv/bin/activate

python -m pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload
```

Backend URLs:
- API: `http://localhost:8000`
- Health: `http://localhost:8000/health`

### 3. Run frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:
- App: `http://localhost:3000`

### 4. Warm up catalog (optional but recommended before demo)

```bash
cd backend
python scripts/warmup_supplements_catalog.py --target 100
```

This seeds DB-first catalog records used by the coverage auditor before live crawl.

## Docker compose

Run the full stack:

```bash
docker compose up --build
```

This starts:
- `frontend` at `http://localhost:3000`
- `backend` at `http://localhost:8000`
- `redis` at `redis://localhost:6379`

Notes:
- `NEXT_PUBLIC_*` values are passed into the frontend image at build time.
- `backend/data` is mounted for SQLite persistence.
- The backend CORS allowlist defaults to localhost frontend origins.

## API surface used by the UI

- `POST /v1/sessions`
- `GET /v1/sessions?limit=&cursor=`
- `GET /v1/sessions/{session_id}`
- `GET /v1/sessions/{session_id}/products`
- `POST /v1/chat`
- `POST /v1/runs/{session_id}/resume`
- `GET /v1/recommendations/{session_id}`
- `GET /v1/metrics/runtime`
- `POST /v1/voice/consult`
- `GET /v1/metrics/catalog`

## Testing

Backend:

```bash
cd backend
pytest -q
```

Frontend production check:

```bash
cd frontend
npm run build
```

## Demo references

- Demo runbook: `docs/demo_runbook.md`
- Submission checklist: `docs/submission_checklist.md`

## Suggested judge demo

Use a prompt like:

```text
Find a whey isolate under $90 with third-party testing, low lactose, and no sucralose.
```

Then show:
- landing page auth/session state and theme toggle
- session-bound chat history
- shortlist cards on `/results`
- trace panel, trust radar, source mix, and evidence ledger
- product detail charts and ingredient flags
- evidence reference links
