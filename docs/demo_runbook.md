# Demo Runbook - Agentic Shopping Assistant (Agent Core)

## 1) Start services

### Option A: Docker (recommended)

```bash
docker compose up --build
```

### Option B: Local python

```bash
python -m pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload
```

## 2) Verify health

```bash
curl http://127.0.0.1:8000/health
```

Expected: `status=ok`, model IDs present, checkpoint backend visible.

## 3) Run guided demo script

From repo root:

```bash
python backend/scripts/demo_walkthrough.py
```

The script will run:
- session creation
- initial chat turn (follow-up expected)
- resume turn with full constraints
- recommendation retrieval
- full snapshot retrieval

## 4) Manual fallback scenario (automation blocked)

Send chat message with `exclude captcha` and verify:
- recommendation still returns `WAIT` or `AVOID`
- risk flags include automation blocker
- no payment action is executed

## 5) Judge-facing talking points

- Multi-agent orchestration: planner -> review -> visual -> price/logistics -> decision.
- Safety policy: checkout automation always stops before payment.
- Explainability: recommendation payload includes score breakdown and risk flags.
- Resilience: system continues with graceful degradation when automation is blocked.

