# Release Checklist - AgentCart

## Product checks

- [ ] Landing login and search flow work on `http://localhost:3000`
- [ ] `/results` creates and loads session data from API
- [ ] Follow-up chat continues in the same session
- [ ] `/history` reopens prior sessions from `GET /v1/sessions`
- [ ] `/product/[id]` renders analysis, charts, and source links
- [ ] Light and dark mode both render correctly on desktop/mobile
- [ ] Browser preflight to API endpoints succeeds from frontend origin
- [ ] No guest-mode path in primary flow

## Backend checks

- [ ] `POST /v1/sessions`
- [ ] `OPTIONS /v1/sessions` returns expected CORS headers
- [ ] `POST /v1/chat`
- [ ] `POST /v1/runs/{session_id}/resume`
- [ ] `GET /v1/sessions/{session_id}`
- [ ] `GET /v1/sessions/{session_id}/products`
- [ ] `GET /v1/recommendations/{session_id}`
- [ ] `GET /v1/metrics/catalog`
- [ ] `pytest -q` passes

## Explainability checks

- [ ] Trace timeline is visible in results or product detail
- [ ] Trust score dimensions are visible
- [ ] Product signals and risk flags are visible
- [ ] Source links are clickable
- [ ] Chat messages expose expandable structured reasoning (no raw CoT)

## Safety checks

- [ ] No payment action is executed
- [ ] Risk flags/blockers appear when confidence is low
- [ ] `NEED_DATA` path resumes safely in the same session

## Delivery checks

- [ ] README reflects current architecture and setup
- [ ] Docker compose starts frontend, backend, and redis
- [ ] Warmup script can seed target catalog volume
- [ ] End-to-end flow runs without manual state resets
