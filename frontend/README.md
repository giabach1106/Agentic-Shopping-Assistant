# Frontend - AgentCart

This frontend is a typed Next.js client for the AgentCart backend.

## What it does

- creates and resumes agent sessions
- binds chat, recommendations, history, and product detail to one `sessionId`
- renders trust metrics, source-mix charts, ABSA charts, ranked evidence tables, and structured trace output
- shows ingredient analysis and source references for supplements and whey products
- supports persistent dark/light theme selection

## Required env

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_COGNITO_DOMAIN=your-domain.auth.us-east-1.amazoncognito.com
NEXT_PUBLIC_COGNITO_CLIENT_ID=your-client-id
NEXT_PUBLIC_COGNITO_REDIRECT_URI=http://localhost:3000
```

Backend note:

```env
AGENT_CORS_ALLOW_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
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

- If Cognito env vars are present, the UI requires login before creating sessions.
- If Cognito env vars are omitted, the UI falls back to guest mode for local demo work.
- The backend currently parses bearer token claims but does not fully enforce JWT verification.
- `NEXT_PUBLIC_*` variables must be available when building Docker images because they are inlined into the client bundle.
