# Frontend - AgentCart

This frontend is a typed Next.js client for the AgentCart backend.

## What it does

- creates and resumes agent sessions
- binds chat, recommendations, history, and product detail to one `sessionId`
- renders trust metrics, source-mix charts, ABSA charts, ranked evidence tables, and structured trace output
- shows ingredient analysis and source references for supplements and whey products
- supports persistent dark/light theme selection

## Required env

Create root `.env` (repository root):

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_COGNITO_DOMAIN=your-domain.auth.us-east-1.amazoncognito.com
NEXT_PUBLIC_COGNITO_CLIENT_ID=your-client-id
NEXT_PUBLIC_COGNITO_REDIRECT_URI=http://localhost:3000
NEXT_PUBLIC_USE_COGNITO_HOSTED_LOGOUT=false
```

Backend note:

```env
AGENT_CORS_ALLOW_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
AGENT_REQUIRE_AUTH=true
```

## Run locally

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

## Production check

```bash
npm run build
npm run start
```

## Main routes

- `/`: minimal landing page, auth state, new search, and resume CTA
- `/results`: session-bound recommendation flow with charts and decision console
- `/history`: session archive from backend
- `/product/[id]`: product detail for a candidate within a session

## Notes

- This sprint enforces strict auth: no guest mode for `/v1/*` flows.
- Missing Cognito env values surface explicit setup errors in the UI shell.
- The backend enforces bearer token presence and required claims for protected routes.
- `NEXT_PUBLIC_*` variables must be available when building Docker images because they are inlined into the client bundle.
- Docker build arg `REQUIRE_COGNITO_ENV=true` can be used in CI to hard-fail when Cognito vars are missing.
- Frontend now falls back to loading `../.env`, so `frontend/.env.local` is optional.
- Hosted logout is only enabled when both of these are set: `NEXT_PUBLIC_USE_COGNITO_HOSTED_LOGOUT=true` and `NEXT_PUBLIC_COGNITO_LOGOUT_URI`.
