# Submission Checklist - AgentCart

## Product checks

- [ ] Landing page login and search flow work on `http://localhost:3000`
- [ ] `/results` creates a session and loads recommendation data from the API
- [ ] Sidebar follow-up chat resumes the same session
- [ ] `/history` reopens prior sessions from `GET /v1/sessions`
- [ ] `/product/[id]` renders ingredient analysis, charts, and source references
- [ ] Dark mode and light mode both render correctly on desktop and mobile

## Backend checks

- [ ] `POST /v1/sessions` works
- [ ] `POST /v1/chat` works
- [ ] `POST /v1/runs/{session_id}/resume` works
- [ ] `GET /v1/sessions/{session_id}` works
- [ ] `GET /v1/sessions/{session_id}/products` works
- [ ] `GET /v1/recommendations/{session_id}` returns decision payload
- [ ] `pytest -q` passes

## Explainability checks

- [ ] Trace timeline is visible in results or product detail
- [ ] Trust score dimensions are visible
- [ ] Ingredient red flags and beneficial signals are visible
- [ ] Source links are clickable from the UI
- [ ] The demo explains DB-first evidence reuse before fresh crawling

## Safety checks

- [ ] No payment action is executed
- [ ] Risk flags or blockers are shown when evidence is weak
- [ ] `NEED_DATA` path can be resumed safely from the same session

## Demo package

- [ ] README matches the current architecture
- [ ] Docker compose starts frontend, backend, and Redis
- [ ] Demo script uses the whey / supplements lane
- [ ] Judge walkthrough includes one normal path and one cautious fallback path
