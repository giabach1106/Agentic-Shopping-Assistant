# AgentCart

AgentCart is a session-based shopping assistant web app. Users can sign in, describe buying constraints, get ranked candidates, and keep the full decision trail in one place.

## Core capabilities

- Session-bound chat and follow-up workflow
- Constraint-aware candidate ranking (budget, rating, delivery preference)
- Product shortlist and product analysis pages
- Explainable scoring with trace timeline and evidence tables
- History page to reopen prior sessions
- Light and dark theme support

## Stack

- Frontend: Next.js 15, React 19, Tailwind CSS 4, Recharts
- Backend: FastAPI, LangGraph orchestration, SQLite evidence store, Redis checkpoints
- Auth: Amazon Cognito (frontend hosted flow + bearer token to API)

## Repository layout

- `frontend/`: Next.js application
- `backend/`: FastAPI services, agents, collectors, tests, scripts
- `docs/`: operational runbooks and release checklists

## Environment setup

Use a single root `.env` file:

```env
MOCK_MODEL=true
AWS_REGION=us-east-1
AGENT_SQLITE_PATH=backend/data/agent_memory.sqlite3
AGENT_REDIS_URL=redis://localhost:6379/0
AGENT_CORS_ALLOW_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
AGENT_REQUIRE_AUTH=true
AGENT_VERIFY_JWT_SIGNATURE=true
COGNITO_REGION=us-east-1
COGNITO_USER_POOL_ID=your-user-pool-id
COGNITO_APP_CLIENT_ID=your-client-id
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_COGNITO_DOMAIN=your-domain.auth.us-east-1.amazoncognito.com
NEXT_PUBLIC_COGNITO_CLIENT_ID=your-client-id
NEXT_PUBLIC_COGNITO_REDIRECT_URI=http://localhost:3000
NEXT_PUBLIC_USE_COGNITO_HOSTED_LOGOUT=false
# NEXT_PUBLIC_COGNITO_LOGOUT_URI=http://localhost:3000
```

Notes:

- `NEXT_PUBLIC_*` variables are loaded at frontend container startup via `public/runtime-config.js` (runtime env), so domain changes do not require a frontend rebuild.
- Frontend and backend both fall back to root `.env`, so local per-folder env files are optional.
- If you enable hosted Cognito logout, set both `NEXT_PUBLIC_USE_COGNITO_HOSTED_LOGOUT=true` and `NEXT_PUBLIC_COGNITO_LOGOUT_URI`.
- `AGENT_CORS_ALLOW_ORIGINS` must include frontend origin to pass browser preflight.
- With `AGENT_REQUIRE_AUTH=true`, backend verifies Cognito JWT signature by default. Set `COGNITO_REGION`, `COGNITO_USER_POOL_ID`, and `COGNITO_APP_CLIENT_ID`.

## Run locally

### 1) Backend

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

### 2) Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

- App: `http://localhost:3000`

### 3) Optional catalog warmup

```bash
cd backend
python scripts/warmup_supplements_catalog.py --target 1600
```

This preloads catalog records for faster first-query behavior in local development.

## Docker

```bash
docker compose up --build
```

Services:

- `frontend` at `http://localhost:3000`
- `backend` at `http://localhost:8000`
- `redis` at `redis://localhost:6379`

## API endpoints used by frontend

- `POST /v1/sessions`
- `GET /v1/sessions?limit=&cursor=`
- `GET /v1/sessions/{session_id}`
- `GET /v1/sessions/{session_id}/products`
- `POST /v1/chat`
- `POST /v1/runs/{session_id}/resume`
- `GET /v1/recommendations/{session_id}`
- `GET /v1/metrics/runtime`
- `GET /v1/metrics/catalog`
- `POST /v1/voice/consult`

## Quality checks

Backend:

```bash
cd backend
pytest -q
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```
