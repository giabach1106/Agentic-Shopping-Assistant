# Agentic-Shopping-Assistant

## Backend Agent Core (Sprint 1)

### Option A: Python `venv` (recommended)

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

### Option B: Conda

```bash
conda create -n agent-shop python=3.12 -y
conda activate agent-shop
python -m pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload
```

When running locally, `AGENT_SQLITE_PATH` is resolved from your current working directory.
If you run from repo root, use `AGENT_SQLITE_PATH=backend/data/agent_memory.sqlite3`.
If you run from `backend/`, use `AGENT_SQLITE_PATH=data/agent_memory.sqlite3`.

### Option C: Docker (backend + Redis)

```bash
docker compose up --build
```

This starts:
- `backend` at `http://127.0.0.1:8000`
- `redis` at `localhost:6379`

Docker compose now loads variables from `.env` for backend (including `MOCK_MODEL`, model IDs, AWS region/credentials).  
For local mock-only runs, keep `MOCK_MODEL=true`. For real Bedrock calls, set `MOCK_MODEL=false` in `.env`.
Use Bedrock inference profile IDs available in your account (for example `us.amazon.nova-2-lite-v1:0`).
Recommended realtime defaults:
- `NOVA_DEFAULT_MODEL_ID=us.amazon.nova-2-pro-v1:0`
- `NOVA_FALLBACK_MODEL_ID=us.amazon.nova-2-lite-v1:0`
For strict realtime/fail-closed behavior, set `RUNTIME_MODE=prod`, `MOCK_MODEL=false`, and use a realtime executor backend.

### Test with CLI chatbot

```bash
# run from backend/
python scripts/chat_cli.py
```

Optional: pass existing session id.

```bash
python scripts/chat_cli.py --session-id <SESSION_ID>
```

Optional: inspect agent trace per turn.

```bash
python scripts/chat_cli.py --verbose
python scripts/chat_cli.py --raw-state
```

### Run tests

```bash
cd backend
pytest -q
```

### Notes

- If Redis is not running locally, backend will fall back to in-memory checkpoints and show a warning at startup.
- To remove that warning in local non-docker mode, run Redis and set `AGENT_REDIS_URL=redis://localhost:6379/0`.
- RAG defaults to `inmemory` for local development.
- Set `RAG_BACKEND=chroma` to use local persistent Chroma storage (`RAG_CHROMA_PATH`).
- Set `RAG_BACKEND=bedrock_kb` and `BEDROCK_KB_ID=<your_kb_id>` to use Bedrock Knowledge Bases.
- Ingest local corpus example:
  `python backend/scripts/ingest_local_corpus.py --input backend/data/reviews.sample.jsonl`
- Realtime commerce collector preference is `eBay -> Walmart -> Amazon` (Amazon is optional and non-blocking when alternative product sources are available).

### Useful API endpoints

- `POST /v1/sessions`: create session ID
- `POST /v1/chat`: run one agent turn
- `POST /v1/runs/{session_id}/resume`: resume from checkpoint (requires `message` if follow-up is pending)
- `GET /v1/sessions/{session_id}`: full snapshot + checkpoint state
- `GET /v1/recommendations/{session_id}`: latest decision payload for UI consumption
- `GET /v1/metrics/runtime`: runtime telemetry (calls, fallback count, latency, estimated cost)
- `POST /v1/voice/consult`: optional Sonic-style consultation (text-simulated voice response)

### Backend API response contract

- `POST /v1/chat` and `GET /v1/recommendations/{session_id}` return:
  - `status`: `OK | NEED_DATA | ERROR`
  - `decision`: nullable (null when fail-closed)
  - `scientificScore`: `ratingReliability`, `spamAuthenticity`, `absaAlignment`, `visualReliability`, `finalTrust`
  - `evidenceStats`: `sourceCoverage`, `freshnessSeconds`, `reviewCount`, `ratingCount`, `missingFields`
  - `trace`, `missingEvidence`, `blockingAgents`

### Demo utilities

- Guided walkthrough: `python backend/scripts/demo_walkthrough.py`
- Demo runbook: [`docs/demo_runbook.md`](docs/demo_runbook.md)
- Submission checklist: [`docs/submission_checklist.md`](docs/submission_checklist.md)
