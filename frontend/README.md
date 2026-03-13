# Frontend - AgentCart

Typed Next.js client for the AgentCart API.

## Features

- Start and resume shopping sessions
- Session-bound chat, recommendation, and product analysis flow
- Charts for trust metrics and evidence diagnostics
- Structured reasoning panel (expandable message details)
- History page backed by API session summaries
- Persistent light/dark theme

## Required environment variables

Define these in root `.env`:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_COGNITO_DOMAIN=your-domain.auth.us-east-1.amazoncognito.com
NEXT_PUBLIC_COGNITO_CLIENT_ID=your-client-id
NEXT_PUBLIC_COGNITO_REDIRECT_URI=http://localhost:3000
NEXT_PUBLIC_USE_COGNITO_HOSTED_LOGOUT=false
```

Backend must also allow frontend origin:

```env
AGENT_CORS_ALLOW_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
AGENT_REQUIRE_AUTH=true
```

## Local run

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

## Production check

```bash
npm run lint
npm run build
npm run start
```

## Main routes

- `/`: landing, auth state, new search
- `/results`: session analysis, shortlist, recommendation, live chat
- `/history`: saved sessions
- `/product/[id]`: per-product analysis within a session

## Notes

- Main flow is strict-auth (`/v1/*` requires token).
- Missing Cognito env values surface explicit setup errors.
- `NEXT_PUBLIC_*` values must be present at Docker build time.
- Frontend falls back to root `.env`, so `frontend/.env.local` is optional.
- Hosted logout only works if both `NEXT_PUBLIC_USE_COGNITO_HOSTED_LOGOUT=true` and `NEXT_PUBLIC_COGNITO_LOGOUT_URI` are set.
