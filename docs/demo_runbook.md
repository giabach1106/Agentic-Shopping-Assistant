# Operations Runbook - AgentCart

## 1) Start services

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

## 2) Verify health and auth

- Backend health: `http://localhost:8000/health`
- Frontend: `http://localhost:3000`
- Catalog metrics: `http://localhost:8000/v1/metrics/catalog` (requires auth)
- Confirm Cognito login callback stores token and session calls succeed.

## 3) Optional catalog warmup

```bash
cd backend
python scripts/warmup_domain_corpus.py --domain supplement --target 1600
python scripts/warmup_domain_corpus.py --domain chair --target 600
python scripts/warmup_domain_corpus.py --domain desk --target 600
```

Use this when you want richer catalog coverage before traffic or local validation.

## 4) Smoke flow

1. Login on landing page.
2. Submit a shopping prompt.
3. On `/results`, verify:
   - session metadata and trust cards
   - compact recommendation card
   - horizontal shortlist cards with product images
   - follow-up chat and expandable reasoning details
4. Open a shortlist item in `/product/[id]`.
5. Confirm source links and diagnostics render.
6. Reopen the same session from `/history`.

## 5) If data is sparse

- Send one clarifying follow-up in the same session.
- Re-run warmup with a larger target.
- Check `/v1/metrics/catalog` for source distribution and freshness.
